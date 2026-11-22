"""The multiplayer recipe: a guest converts its own dump exactly as the host did.

Two players can play one converted game together only when their executables compute the same frames
(`simulation_identity`). The host never sends its game. It sends a recipe, a ROM-free document of a few kB, and the
guest's converter converts the guest's OWN copy of the same dump in recipe mode, then compares identities.

What a recipe carries (`make_recipe`), and nothing else:

* its format and version, the host's converter version and a date;
* the machine, the dump's SHA-256, the dump's file name without its extension and the game's title (names only:
  the Master System reads the video standard and the light gun from the file name, so the guest converts a private
  copy of its dump under the host's name);
* the run-changing options of the host's export, as its simulation identity recorded them;
* the paths the host's conversion used for this one game, as a version 3 exchange document of one game
  (`knowledge_exchange.game_document`): numbers only, positions in the ROM, never ROM bytes, checked on both sides
  by the validators of path sharing (`knowledge_exchange.validate_exchange`);
* the host's simulation identity, to check the result against.

Applying one (`apply_recipe`): the checks first (the document validates; the same converter version; the guest's
dump has the recipe's SHA-256), then one conversion in recipe mode, in a process of its own:

* a library of its own (RETRO_RECOMP_LIBRARY_DIR), which switches the guest's qualified and imported banks off;
* the recipe's paths imported by the ordinary import into banks of its own (`knowledge.RECIPE_VARIABLE`), read in
  place of the guest's;
* nothing read from the guest's earlier exports or gameplay records (`core.import_previous`, `feedback.ingest`);
* one pass on the quick routes, from the paths given (the plan of an upgrade without rediscovery): what is
  compiled is what the recipe says, not what this conversion could learn; its checks against the reference still
  run, and a conversion that fails them is not retried without the paths;
* its own output folder, which may not be the guest's games folder: the guest's usual export of the game, its
  library and its banks are not written, and nothing of this conversion is shared again (the library it learned
  into is removed with the work folder).

The answer says whether the guest's new simulation identity equals the recipe's. Equal identities are equal inputs
of the simulation, not a proof of determinism.

Machines: `MACHINES` are in; `LEFT_OUT` gives, for every other machine, why it is not (what was read in the code,
nothing more). This module is hashed by no stamp (`stamp_inputs.INTERFACE_MODULES`): it runs conversions and
changes nothing a game is or does.
"""
from __future__ import annotations

import copy
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

FORMAT = 'retro-recomp-recipe'
VERSION = 1
SUFFIX = '.rrrecipe'
# A recipe travels over the lobby's stream: bounded well below a paths file (knowledge.MAX_BYTES).
MAX_BYTES = 16 * 1024 * 1024
NAME_LIMIT = 160
TEXT_LIMIT = 64
KEYS = frozenset(('format', 'version', 'converter', 'created_utc', 'system', 'rom_sha256', 'name', 'title',
                  'options', 'identity', 'paths'))
WORK_FOLDER = 'recipe-work'
INTERNAL_COMMAND = '_recipe-convert'

# The machines in recipe mode: the extension their private copy of the dump is written with.
MACHINES = {'sms': '.sms', 'gg': '.gg'}

_OWN_RECORD = ('its conversion also reads a record or observations of its own in the library folder of the game, beside '
               'the banks; how that union travels as numbers and is rebuilt on the other side is not established')
_CARTRIDGE = ('its conversion reads learned files of its own in the library (code built in RAM is kept there as '
              'bytes, and what has no position in the ROM cannot travel as numbers); recipe mode is not established '
              'for its converter')
# Why each other machine is not in recipe mode: what the code shows, nothing more.
LEFT_OUT = {
    'gb': _CARTRIDGE, 'gbc': _CARTRIDGE, 'nes': _CARTRIDGE, 'md': _CARTRIDGE, 'snes': _CARTRIDGE,
    'ng': ('its paths are keyed by cartridge and BIOS together and read by neogeo_knowledge, which tests '
           'RETRO_RECOMP_LIBRARY_DIR itself; recipe mode is not established for it'),
    'cps1': _OWN_RECORD, 'cps2': _OWN_RECORD, 'x68': _OWN_RECORD, 'pce': _OWN_RECORD, 'msx': _OWN_RECORD,
    'msx2': _OWN_RECORD, 'msx2plus': _OWN_RECORD, 'amiga': _OWN_RECORD, 'a1200': _OWN_RECORD,
    'atarist': _OWN_RECORD, 'gba': _OWN_RECORD, 'psx': _OWN_RECORD,
    'pcecd': ('its paths are keyed by the disc and the System Card together (the disc is a CHD, a CUE sheet with its tracks or an ISO, not a dump with a ROM hash), and its conversion '
              'reads observations of its own in the library folder of the game; how they travel as numbers and are rebuilt on the other side is not established'),
    'n64': 'its conversion keeps its own files in the library folder of the game; recipe mode is not established for it',
    'sg1000': 'experimental, developer only: it has a multiplayer session (rollback) but no path record, so recipe mode is not established for it',
    'coleco': 'experimental, developer only: it has a multiplayer session (rollback) but no path record, so recipe mode is not established for it',
    'scummvm': 'emulated: it translates no code and has no path to carry; recipe mode is not wired for it',
    'zxs': 'in development: the ZX Spectrum converts nothing yet, so it has no conversion to replay; recipe mode is not established for it',
    'cpc': 'in development: no game is converted yet; recipe mode is not established for it',
}


class RecipeError(ValueError):
    """A recipe that is refused, with a reason a player can read. `kind`: 'invalid' (the document), 'converter'
    (another converter version), 'rom' (another dump), 'machine' (not in recipe mode), 'record' (the host's paths
    cannot travel), 'output' (the folder), 'conversion' (the conversion itself failed)."""

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def _need(condition, reason: str, kind: str = 'invalid') -> None:
    if not condition:
        raise RecipeError(kind, reason)


def _text(value, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and value.isprintable()


def _file_name(value) -> bool:
    """A file name without its extension and without a folder: nothing that could leave the work folder."""
    return (_text(value, NAME_LIMIT) and value == value.strip() and not value.endswith('.')
            and not set(value) & set('<>:"/\\|?*') and value not in ('.', '..'))


def _profile(system):
    from .systems import ALL_PROFILES
    known = {profile.id: profile for profile in ALL_PROFILES}
    _need(isinstance(system, str) and system in known, 'This recipe names a machine this converter does not know.')
    _need(system in MACHINES, f'{known[system].name} is not in recipe mode: {LEFT_OUT.get(system, "not established")}.',
          'machine')
    return known[system]


def _options(profile, options) -> dict:
    """The run-changing options, exactly the names the machine declares; plain values only."""
    from .simulation_identity import run_options
    expected = run_options(profile, {})
    _need(isinstance(options, dict) and set(options) == set(expected), 'Invalid options in the recipe.')
    choices = {key.name: key.choices for key in profile.option_keys if key.changes_run and key.choices}
    for name, value in options.items():
        _need(value is None or type(value) in (bool, int) or _text(value, TEXT_LIMIT), 'Invalid option in the recipe.')
        _need(name not in choices or value in choices[name], 'Invalid option in the recipe.')
    return dict(options)


def _paths(system: str, identity: str, paths) -> dict:
    """The recipe's paths as the import takes them (the schema 1 projection of the version 3 document), checked by
    the validators of path sharing. They may name this one game only."""
    from .knowledge_exchange import LATEST_VERSION, validate_exchange
    try:
        document = validate_exchange(copy.deepcopy(paths))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise RecipeError('invalid', f'The paths of this recipe are refused: {str(error) or type(error).__name__}') from None
    _need(document['version'] == LATEST_VERSION and not document['unreadable_games'], 'The paths of this recipe are refused.')
    for part in (document['knowledge']['consoles'], document['observations']):
        _need(all(name == system and set(games) <= {identity} for name, games in part.items()),
              'The paths of this recipe name another game.')
    return document


def validate_recipe(document) -> dict:
    """The recipe, checked whole (a copy), or RecipeError. A recipe of another converter version is refused as
    such before anything else of it is read: its format may be another."""
    from .path_profiles import HEX64
    from .simulation_identity import SCHEMA
    from .knowledge_exchange import TITLE_LIMIT
    _need(isinstance(document, dict) and document.get('format') == FORMAT, 'Not a Retro-Recomp multiplayer recipe.')
    converter = document.get('converter')
    _need(_text(converter, TEXT_LIMIT), 'Invalid recipe header.')
    _need(converter == __version__,
          f'This recipe was made by Retro-Recomp {converter}; this is Retro-Recomp {__version__}: '
          'both players need the same version.', 'converter')
    _need(type(document.get('version')) is int and document['version'] == VERSION and set(document) == KEYS,
          'Invalid recipe.')
    _need(_text(document['created_utc'], TEXT_LIMIT), 'Invalid recipe header.')
    profile = _profile(document['system'])
    identity = document['rom_sha256']
    _need(isinstance(identity, str) and HEX64.fullmatch(identity), 'Invalid dump identity in the recipe.')
    _need(_file_name(document['name']), 'Invalid dump name in the recipe.')
    _need(_text(document['title'], TITLE_LIMIT), 'Invalid title in the recipe.')
    simulation = document['identity']
    _need(isinstance(simulation, dict) and set(simulation) == {'schema', 'identity'}
          and simulation['schema'] == SCHEMA and isinstance(simulation['identity'], str)
          and HEX64.fullmatch(simulation['identity']), 'Invalid simulation identity in the recipe.')
    clean = {name: document[name] for name in ('format', 'version', 'converter', 'created_utc', 'system',
                                               'rom_sha256', 'name', 'title')}
    clean['options'] = _options(profile, document['options'])
    clean['identity'] = dict(simulation)
    _paths(profile.id, identity, document['paths'])
    clean['paths'] = copy.deepcopy(document['paths'])
    return clean


def recipe_bytes(recipe: dict) -> bytes:
    """The recipe as it travels and as it is stored: gzip of its canonical JSON, bounded."""
    raw = json.dumps(validate_recipe(recipe), separators=(',', ':'), sort_keys=True, ensure_ascii=True).encode('ascii')
    _need(len(raw) <= MAX_BYTES, 'The recipe exceeds its size limit.', 'record')
    return gzip.compress(raw, compresslevel=9, mtime=0)


def parse_recipe(data: bytes) -> dict:
    """`recipe_bytes` the other way: bounded, then validated."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        _need(len(raw) <= MAX_BYTES, 'The recipe exceeds its size limit.')
        document = json.loads(raw)
    except (OSError, EOFError, ValueError, RecursionError) as error:
        if isinstance(error, RecipeError):
            raise
        raise RecipeError('invalid', 'Not a Retro-Recomp multiplayer recipe.') from None
    return validate_recipe(document)


def write_recipe(recipe: dict, destination: Path) -> Path:
    destination = Path(destination)
    data = recipe_bytes(recipe)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, destination)
    return destination


def read_recipe(path: Path) -> dict:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise RecipeError('invalid', 'The recipe exceeds its size limit.')
        data = path.read_bytes()
    except OSError as error:
        raise RecipeError('invalid', f'The recipe cannot be read: {error}') from None
    return parse_recipe(data)


def _read_dump(profile, rom_path: Path):
    try:
        return profile.read_rom(Path(rom_path))
    except Exception as error:   # the machine's reader says why in its own words
        raise RecipeError('rom', f'The dump cannot be read: {error}') from None


def _sega_paths(profile, rom, report: dict) -> tuple[dict, list]:
    """Master System and Game Gear: the record of everything the conversion used (its own journals, the banks and
    the gameplay records together: `knowledge_build.build_record(offered=True)`), or the reason it cannot travel."""
    from .knowledge_build import build_record, engines
    _need(report.get('backend') == 'banked',
          'This export was made with the functions backend, which leaves received paths aside '
          '(systems.master_system.convert_checked): it has no recipe. Convert the game with the default backend.',
          'record')
    profiles = (report.get('learning') or {}).get('native_profiles') or {}
    _need(not profiles.get('pending_windows') and not profiles.get('windows_over_limit'),
          'This conversion found code after its last compilation, or more than it compiles: convert the game again, '
          'then make the recipe.', 'record')
    omitted = {'unqualified': 0, 'ram_without_rom_source': 0}
    record = build_record(rom, profile.id, report, engines()[profile.id], omitted, offered=True)
    _need(record is not None,
          "The game's library is not the one this conversion left (another conversion or new observations since): "
          'convert the game again, then make the recipe.', 'record')
    private = omitted['ram_without_rom_source']
    _need(not private,
          f'{private} piece(s) of code this export runs natively were built in RAM by the game and have no position '
          'in its ROM: they cannot travel as numbers, so another player cannot rebuild the same executable.', 'record')
    return record, []


_BUILDERS = {'sms': _sega_paths, 'gg': _sega_paths}


def make_recipe(report_path: Path, rom_path: Path | None = None) -> dict:
    """The recipe of one compiled game of this PC, from its conversion report, its dump (`rom_path`, else the one
    the report names) and the library and banks as the conversion left them. RecipeError when it cannot be made."""
    from .knowledge_exchange import game_document
    from .report_schema import ReportShapeError, read_report
    try:
        report = json.loads(Path(report_path).read_text(encoding='utf-8'))
        simulation = read_report(report)['simulation_identity']
        system = report['system']['id']
        identity = report['rom']['sha256']
        source = Path(rom_path or report['source_rom'])
        name = Path(str(report['rom']['name'])).stem
    except (OSError, ValueError, KeyError, TypeError, ReportShapeError) as error:
        raise RecipeError('invalid', f'This conversion report cannot be read: {error}') from None
    profile = _profile(system)
    _need(report.get('version') == __version__,
          f'This game was converted by Retro-Recomp {report.get("version")}; this is Retro-Recomp {__version__}: '
          'convert it again, then make the recipe.', 'converter')
    _need(isinstance(simulation, dict) and isinstance(simulation.get('identity'), str),
          'This conversion has no simulation identity'
          + (f' ({simulation["reason"]})' if isinstance(simulation, dict) and simulation.get('reason') else '')
          + ': convert the game again, then make the recipe.', 'record')
    rom = _read_dump(profile, source)
    _need(rom.sha256 == identity, f'{source.name} is not the dump this game was converted from (SHA-256 {identity}).', 'rom')
    _need(_file_name(name), 'The name of this dump cannot be carried by a recipe.', 'record')
    title = str((report.get('windows_metadata') or {}).get('ProductName') or name)
    record, rows = _BUILDERS[system](profile, rom, report)
    try:
        paths = game_document(system, identity, record, rows, title)
    except (ValueError, TypeError, KeyError) as error:
        raise RecipeError('record', f'The paths of this game cannot travel: {error}') from None
    recipe = {'format': FORMAT, 'version': VERSION, 'converter': __version__,
              'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'system': system, 'rom_sha256': identity, 'name': name, 'title': title,
              'options': dict(simulation['options']),
              'identity': {'schema': simulation['schema'], 'identity': simulation['identity']}, 'paths': paths}
    recipe_bytes(recipe)   # validated and within the size a recipe may have
    return recipe


def check_recipe(recipe, rom_path: Path):
    """The checks before any conversion: the document validates, the converter version is the host's, the dump
    given has the recipe's SHA-256. Returns (the validated recipe, the dump as the machine reads it)."""
    recipe = validate_recipe(recipe)
    rom = _read_dump(_profile(recipe['system']), rom_path)
    _need(rom.sha256 == recipe['rom_sha256'],
          f'This game needs {recipe["name"]} (SHA-256 {recipe["rom_sha256"]}); the file given is another dump '
          f'(SHA-256 {rom.sha256}).', 'rom')
    return recipe, rom


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _check_output(output: Path) -> None:
    """The recipe's export has a folder of its own: never the player's games folder (his usual export of the game
    would be replaced), a folder his gameplay records are searched in, or the converter's data."""
    from .paths import data_directory, feedback_search_paths, games_root, load_preferences, preferred_games_root
    preferences = load_preferences()
    protected = {games_root().resolve(), preferred_games_root(preferences)[0].resolve(), data_directory().resolve(),
                 *(path.resolve() for path in feedback_search_paths(preferences).values())}
    for root in protected:
        _need(not _within(output, root) and not _within(root, output),
              f'A recipe converts into a folder of its own, outside {root}.', 'output')


def _command(job: Path) -> list:
    if getattr(sys, 'frozen', False):
        return [sys.executable, INTERNAL_COMMAND, str(job)]
    from .paths import ROOT     # the roots come from paths.py, never from a module's own file
    return [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), INTERNAL_COMMAND, str(job)]


def apply_recipe(recipe, rom_path: Path, output: Path, *, language: str = 'en', compress: bool | None = None,
                 cover: bool = False, emit=lambda message: None) -> dict:
    """Convert this player's own dump as the recipe says, into `output`. `recipe` is a recipe or the path of one.
    RecipeError when it is refused or the conversion fails. The answer: `same` (the new simulation identity equals
    the recipe's), `identity`, `expected`, `reason` (why there is no identity, if none), `report`, `executable`,
    `imported` (what the import of the recipe's paths counted)."""
    from .knowledge import RECIPE_VARIABLE
    from .packing import compression_from_preferences
    from .paths import ROOT, load_preferences
    from .report_schema import read_report
    from .simulation_identity import same_simulation
    recipe, rom = check_recipe(read_recipe(recipe) if isinstance(recipe, (str, os.PathLike)) else recipe, rom_path)
    output = Path(output).resolve()
    _check_output(output)
    work = output / WORK_FOLDER
    shutil.rmtree(work, ignore_errors=True)
    try:
        (work / 'rom').mkdir(parents=True)
        # This player's own dump, under the host's name (the Master System reads the standard and the light gun
        # from it): a private copy, removed with the work folder.
        dump = work / 'rom' / (recipe['name'] + MACHINES[recipe['system']])
        dump.write_bytes(rom.data)
        job = work / 'job.json'
        job.write_text(json.dumps({
            'recipe': recipe, 'rom': str(dump), 'output': str(output), 'language': language, 'cover': bool(cover),
            'compress': compression_from_preferences(load_preferences()) if compress is None else bool(compress),
            'result': str(work / 'result.json')}), encoding='utf-8')
        environment = dict(os.environ)
        for name in ('SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_KEEP_BUILD'):
            environment.pop(name, None)
        environment['RETRO_RECOMP_LIBRARY_DIR'] = str(work / 'library')
        environment[RECIPE_VARIABLE] = str(work / 'knowledge')
        if getattr(sys, 'frozen', False):
            environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        child = subprocess.Popen(_command(job), cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                 errors='replace',
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        lines = []
        for line in child.stdout:
            lines.append(line.rstrip())
            emit(lines[-1])
        child.wait()
        try:
            result = json.loads((work / 'result.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            result = {'status': 'error', 'message': '\n'.join(lines[-8:]) or f'exit code {child.returncode}'}
        _need(result.get('status') == 'success', f'The recipe conversion failed: {result.get("message")}', 'conversion')
        simulation = read_report(Path(result['report']))['simulation_identity']
        return {'same': same_simulation(simulation, recipe['identity']),
                'identity': (simulation or {}).get('identity'), 'expected': recipe['identity']['identity'],
                'reason': (simulation or {}).get('reason'), 'report': result['report'],
                'executable': result['executable'], 'imported': result.get('imported')}
    finally:
        # The library this conversion learned into, the recipe's banks and the private copy of the dump.
        shutil.rmtree(work, ignore_errors=True)


def run_job(job_path: Path) -> int:
    """The conversion itself, in the process `apply_recipe` starts (RetroRecomp.py, INTERNAL_COMMAND): recipe mode
    is its environment, set before anything of the converter is read."""
    from . import knowledge, packing
    from .batch import convert_batch, identify
    from .knowledge_exchange import import_document
    from .paths import console_options, load_preferences
    job = json.loads(Path(job_path).read_text(encoding='utf-8'))
    result = {'status': 'error', 'message': ''}
    try:
        if knowledge.recipe_directory() is None:
            raise RecipeError('conversion', f'{INTERNAL_COMMAND} runs in recipe mode only.')
        recipe = validate_recipe(job['recipe'])
        # The ordinary import, into the recipe's own banks (knowledge.imported_path in recipe mode).
        result['imported'] = import_document(copy.deepcopy(recipe['paths']))
        item = identify(Path(job['rom']), recipe['system'])
        if item.error or item.sha256 != recipe['rom_sha256']:
            raise RecipeError('rom', item.error or 'The dump is not the one the recipe names.')
        item.title = recipe['title']
        packing.set_compression(bool(job['compress']))
        saved = load_preferences()
        # The machines' own options as the command line gives them: switches at their default, this player's
        # firmware paths, the choices at their default; then the recipe's run-changing options over them.
        keywords = {key.name: bool(key.default) for _, key in console_options('flag')}
        for _, key in console_options('path', 'choice'):
            keywords[key.name] = saved.get(key.name) if key.kind == 'path' else key.default
        keywords.update(recipe['options'])
        record = convert_batch([item], Path(job['output']), force=True, prepare_shared=True, emit=print,
                               passes=1, scan_level='quick', backend='banked', profile=None,
                               language=job['language'], boxart_dir=None, online_cover=False,
                               use_cover=bool(job['cover']), icon_tags=True, **keywords)
        game = record['games'][0]
        result.update(status=game['status'], message=game.get('message', ''), report=game.get('report'),
                      executable=game.get('executable'))
    except Exception as error:
        result['message'] = str(error) or type(error).__name__
    Path(job['result']).write_text(json.dumps(result), encoding='utf-8')
    return 0 if result['status'] == 'success' else 1
