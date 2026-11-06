"""Export of an adventure game as one executable: the ScummVM runtime with the player's game files appended (docs/SCUMMVM.md).

Retro-Recomp's own code (MIT). It never links or includes ScummVM: it starts the separately built GPL runtime
(retrorecomp/scummvm_build.py, native/scummvm) as a program to ask which game a folder holds, and appends the folder's files,
byte for byte and uncompressed, to a copy of that runtime. One generic method for every game:

* ScummVM's own detection (`--detect`) says which game the folder holds: gameid, engine, language, platform, description;
* several candidates are never resolved by code: the player's choice (1-based) is required and stored in the manifest;
* the runtime is the build family of the detected engine (scummvm_build.family_for), never a per-game list;
* the exe is named after the detected title the way the other machines name theirs; its id is a digest of the folder's names
  and sizes; the pack, the launch manifest and datas/ are the same for every game.

Pack layout (read by native/scummvm, backends/fs/packed): [program][file data...][index][trailer], trailer = b'RRADVPK1' +
u64 index offset + u64 index size; index entry = u16 path length, UTF-8 path with '/', u64 offset, u64 size (little endian).
The launch manifest is the pack file '.rr/launch.ini'.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PACK_MAGIC = b'RRADVPK1'
MANIFEST = '.rr/launch.ini'
CHUNK = 8 * 1024 * 1024
# Files of the player's folder that are not game data: the Batocera launcher stub.
SKIPPED_SUFFIXES = ('.scummvm',)
LANGUAGES = {'English', 'French', 'German', 'Italian', 'Spanish', 'Czech', 'Hebrew', 'Russian', 'Polish', 'Japanese',
             'Korean', 'Chinese', 'Portuguese', 'Swedish', 'Dutch', 'Hungarian', 'Danish', 'Norwegian', 'Finnish', 'Greek',
             'Catalan', 'Basque', 'Croatian', 'Turkish', 'Ukrainian', 'Belarusian', 'Arabic', 'Persian'}
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_LINE = re.compile(r'^(\w+):(\S+)\s+(.*?)\s+((?:\\\\|[A-Za-z]:|/).*)$')


class ScummvmExportError(RuntimeError):
    pass


@dataclass
class Candidate:
    engine: str
    gameid: str
    description: str
    title: str
    language: str = ''
    platform: str = ''

    def as_dict(self) -> dict:
        return {'engine': self.engine, 'gameid': self.gameid, 'description': self.description, 'title': self.title,
                'language': self.language, 'platform': self.platform}


@dataclass
class Export:
    exe: Path
    candidate: Candidate
    choice: int
    candidates: list = field(default_factory=list)
    game_id: str = ''
    datas_name: str = ''
    family: str = ''
    files: int = 0
    data_bytes: int = 0


# --- detection (ScummVM's own tables, through the detection runtime) ---------------------------------------------------

def parse_detection(output: str, folder: Path) -> list[Candidate]:
    """The candidates ScummVM's `--detect` prints for exactly `folder` (sub-folders of a recursive listing are ignored)."""
    root = os.path.normcase(os.path.normpath(str(folder)))
    found: list[Candidate] = []
    for line in output.splitlines():
        match = _LINE.match(line.strip())
        if not match:
            continue
        engine, gameid, description, path = match.groups()
        if os.path.normcase(os.path.normpath(path.strip())) != root:
            continue
        tail = re.search(r'\(([^()]*)\)\s*$', description)
        tokens = tail.group(1).split('/') if tail else []
        found.append(Candidate(engine, gameid, description.strip(),
                               description[:tail.start()].strip() if tail else description.strip(),
                               next((t for t in tokens if t in LANGUAGES), ''),
                               '/'.join(t for t in tokens if t not in LANGUAGES)))
    return found


def detect(folder: Path, runtime: Path, timeout: int = 900) -> list[Candidate]:
    """Ask ScummVM's own detection (the separate GPL program) which game `folder` holds; nothing is written in `folder`."""
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', RR_NO_DIALOGS='1')
    with tempfile.TemporaryDirectory() as scratch:
        config = Path(scratch) / 'detect.ini'
        result = subprocess.run([str(runtime), f'--config={config}', '--detect', f'--path={folder}'], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                                timeout=timeout, creationflags=NO_WINDOW)
    return parse_detection(result.stdout, folder)


# --- names --------------------------------------------------------------------------------------------------------------

def exe_title(title: str) -> str:
    """The exe name of a detected title, as the other machines spell theirs ("The X" -> "X, The"; no ':' or forbidden
    characters)."""
    text = title.strip()
    if text.lower().startswith('the '):
        text = text[4:] + ', The'
    text = text.replace(': ', ' - ').replace(':', ' -')
    text = re.sub(r'[<>"/\\|?*\x00-\x1f]', '', text)
    return text.strip().rstrip('.') or 'Game'


def datas_name(title: str) -> str:
    """The folder name part under datas/games, as the other machines spell it (words joined by '_')."""
    return re.sub(r'[^A-Za-z0-9]+', '_', exe_title(title)).strip('_') or 'Game'


def game_files(folder: Path) -> list[tuple[str, Path]]:
    """(relative path with '/', file) of every game file of the folder, in a stable order."""
    files = []
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            if name.lower().endswith(SKIPPED_SUFFIXES):
                continue
            full = Path(root) / name
            files.append((full.relative_to(folder).as_posix(), full))
    return files


def folder_id(folder: Path) -> str:
    """First 12 hex digits of SHA-256 over the sorted 'path<TAB>size' lines of the game files (names and sizes only)."""
    lines = sorted(f'{rel}\t{path.stat().st_size}' for rel, path in game_files(folder))
    return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()[:12]


# --- the pack -----------------------------------------------------------------------------------------------------------

def manifest_text(target: str, name: str, game_id: str, choice: int = 1, candidates: int = 1) -> str:
    return f'target={target}\nname={name}\nid={game_id}\nchoice={choice}\ncandidates={candidates}\n'


def write_pack(program: Path, folder: Path, out: Path, manifest: str, extra: tuple = ()) -> tuple[int, int]:
    """Copy `program` to `out` and append the folder's files byte for byte, the manifest and the index.
    Returns (files, data bytes). `extra` adds (pack path, bytes) members (authored test data)."""
    entries: list[tuple[str, int, int]] = []
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + '.part')
    with open(program, 'rb') as source, open(temporary, 'wb') as target:
        while block := source.read(CHUNK):
            target.write(block)
        for rel, path in game_files(folder):
            start, size = target.tell(), 0
            with open(path, 'rb') as data:
                while block := data.read(CHUNK):
                    target.write(block)
                    size += len(block)
            entries.append((rel, start, size))
        for rel, payload in ((MANIFEST, manifest.encode('utf-8')), *extra):
            entries.append((rel, target.tell(), len(payload)))
            target.write(payload)
        index_offset = target.tell()
        for rel, start, size in entries:
            raw = rel.encode('utf-8')
            target.write(struct.pack('<H', len(raw)) + raw + struct.pack('<QQ', start, size))
        target.write(PACK_MAGIC + struct.pack('<QQ', index_offset, target.tell() - index_offset))
    temporary.replace(out)
    game = [e for e in entries if not e[0].startswith('.rr/')]
    return len(game), sum(e[2] for e in game)


def read_pack_index(exe: Path) -> list[tuple[str, int, int]]:
    """(path, offset, size) of every member of a packed exe; [] when it carries no pack."""
    with open(exe, 'rb') as data:
        data.seek(0, os.SEEK_END)
        total = data.tell()
        if total < 24:
            return []
        data.seek(total - 24)
        trailer = data.read(24)
        if trailer[:8] != PACK_MAGIC:
            return []
        offset, size = struct.unpack('<QQ', trailer[8:])
        if offset + size + 24 > total:
            return []
        data.seek(offset)
        raw = data.read(size)
    entries, position = [], 0
    while position < len(raw):
        (length,) = struct.unpack_from('<H', raw, position)
        name = raw[position + 2:position + 2 + length].decode('utf-8')
        start, length_bytes = struct.unpack_from('<QQ', raw, position + 2 + length)
        entries.append((name, start, length_bytes))
        position += 2 + length + 16
    return entries


# --- the icon (Windows: the resource of the copied runtime, before the pack is appended) --------------------------------

def apply_icon(exe: Path, ico: Path) -> bool:
    """Replace the first icon group of `exe` by the icons of `ico` (UpdateResource). False when not on Windows or when the
    executable has no icon group. Must run before the pack is appended (resource updates rewrite the file)."""
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    RT_ICON, RT_GROUP_ICON = 3, 14
    data = ico.read_bytes()
    reserved, kind, count = struct.unpack_from('<HHH', data, 0)
    if reserved != 0 or kind != 1 or count == 0:
        raise ScummvmExportError(f'{ico} is not an icon file')
    images = []
    for index in range(count):
        w, h, colours, res, planes, bits, size, offset = struct.unpack_from('<BBBBHHII', data, 6 + 16 * index)
        images.append((w, h, colours, res, planes, bits, data[offset:offset + size]))

    group_name, group_language = _first_icon_group(exe)
    if group_name is None:
        return False
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD,
                                       ctypes.c_void_p, wintypes.DWORD]
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    handle = kernel.BeginUpdateResourceW(str(exe), False)
    if not handle:
        raise ScummvmExportError(f'cannot update the resources of {exe} ({ctypes.get_last_error()})')
    first_id = 0x7000
    group = struct.pack('<HHH', 0, 1, len(images))
    ok = True
    for number, (w, h, colours, res, planes, bits, image) in enumerate(images):
        buffer = ctypes.create_string_buffer(image, len(image))
        ok = ok and bool(kernel.UpdateResourceW(handle, RT_ICON, first_id + number, group_language, buffer, len(image)))
        group += struct.pack('<BBBBHHIH', w, h, colours, res, planes, bits, len(image), first_id + number)
    group_buffer = ctypes.create_string_buffer(group, len(group))
    name_argument = group_name if isinstance(group_name, int) else ctypes.c_wchar_p(group_name)
    ok = ok and bool(kernel.UpdateResourceW(handle, RT_GROUP_ICON, name_argument, group_language, group_buffer, len(group)))
    if not kernel.EndUpdateResourceW(handle, not ok):
        raise ScummvmExportError(f'cannot write the icon into {exe} ({ctypes.get_last_error()})')
    return ok


def _first_icon_group(exe: Path):
    """(name or id, language) of the first RT_GROUP_ICON of `exe`, or (None, 0)."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    LOAD_LIBRARY_AS_DATAFILE = 0x2
    kernel.LoadLibraryExW.restype = wintypes.HMODULE
    kernel.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel.FreeLibrary.argtypes = [wintypes.HMODULE]
    module = kernel.LoadLibraryExW(str(exe), None, LOAD_LIBRARY_AS_DATAFILE)
    if not module:
        return None, 0
    found = {'name': None, 'language': 0}
    NameProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    LangProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD,
                                  ctypes.c_void_p)
    kernel.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, NameProc, ctypes.c_void_p]
    kernel.EnumResourceLanguagesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p, LangProc,
                                              ctypes.c_void_p]

    def on_name(_module, _kind, name, _param):
        found['name'] = name if name < 0x10000 else ctypes.wstring_at(name)
        return False

    def on_language(_module, _kind, _name, language, _param):
        found['language'] = language
        return False

    try:
        kernel.EnumResourceNamesW(module, ctypes.c_void_p(14), NameProc(on_name), None)
        name = found['name']
        if name is not None:
            name_argument = ctypes.c_void_p(name) if isinstance(name, int) else ctypes.c_wchar_p(name)
            kernel.EnumResourceLanguagesW(module, ctypes.c_void_p(14), name_argument, LangProc(on_language), None)
    finally:
        kernel.FreeLibrary(module)
    return found['name'], found['language']


# --- licence pack and cover ---------------------------------------------------------------------------------------------

def legal_notice() -> str:
    """The licence pack stored in every exe (pack member '.rr/legal.md'): the written offer, the GPL text, FreeType, SDL2."""
    root = Path(__file__).resolve().parents[1]
    parts = [('Licences of this executable', root / 'licenses' / 'scummvm.md'),
             ('GNU General Public License', root / 'native' / 'scummvm' / 'LICENSE'),
             ('FreeType', root / 'licenses' / 'freetype.md'),
             ('SDL2', root / 'licenses' / 'SDL2.md')]
    return '\n\n'.join(f'# {title}\n\n' + path.read_text(encoding='utf-8') for title, path in parts)


def prepare_cover(candidate: Candidate, game_folder: Path, work: Path, *, online: bool = True, settings: dict | None = None,
                  emit=print) -> tuple[dict, Path | None]:
    """The cover of a detected game through the converter's cover pipeline (artwork.prepare_icon), by title: local images of
    the game folder first, then the configured sources, keyed by the 'scummvm' profile. Returns (artwork report, .ico or None).
    """
    from .artwork import prepare_icon
    from .paths import boxart_cache_directory
    work.mkdir(parents=True, exist_ok=True)
    report = prepare_icon(work, Path(candidate.title + '.rom'), candidate.title, Path(game_folder), online=online,
                          cache_directory=boxart_cache_directory('scummvm'), system_id='scummvm', settings=settings,
                          emit=emit)
    icon = work / 'game.ico'
    return report, (icon if report.get('embedded') and icon.is_file() else None)


# --- one game -----------------------------------------------------------------------------------------------------------

def export_game(folder: Path, out_directory: Path, detect_runtime: Path, runtime_for_family, *, choice: int | None = None,
                icon: Path | None = None) -> Export:
    """Detect, name and pack one game folder into `out_directory`. `runtime_for_family(family) -> Path` gives the runtime.
    Raises ScummvmExportError when nothing is detected or when several candidates need the player's choice."""
    from .scummvm_build import family_for
    folder = Path(folder)
    candidates = detect(folder, detect_runtime)
    if not candidates:
        raise ScummvmExportError(f'ScummVM recognises no game in {folder}')
    if len(candidates) > 1 and choice is None:
        raise ScummvmExportError(f'{len(candidates)} candidates in {folder}: the player must choose one')
    index = (choice or 1) - 1
    if not 0 <= index < len(candidates):
        raise ScummvmExportError(f'choice {choice} is not one of the {len(candidates)} candidates')
    picked = candidates[index]
    family = family_for(picked.engine)
    runtime = Path(runtime_for_family(family))
    name, game_id = datas_name(picked.title), folder_id(folder)
    exe = Path(out_directory) / (exe_title(picked.title) + '.exe')
    if icon is not None and os.name == 'nt':
        staged = exe.with_name(exe.name + '.runtime')
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(runtime.read_bytes())
        apply_icon(staged, icon)
        runtime = staged
    try:
        files, data_bytes = write_pack(runtime, folder, exe, manifest_text(picked.gameid, name, game_id, index + 1,
                                                                          len(candidates)),
                                       extra=(('.rr/legal.md', legal_notice().encode('utf-8')),))
    finally:
        if runtime.name.endswith('.runtime'):
            runtime.unlink(missing_ok=True)
    return Export(exe, picked, index + 1, [c.as_dict() for c in candidates], game_id, name, family, files, data_bytes)


def report_data(export: Export, runtime_identity: dict, artwork: dict | None = None) -> dict:
    """The adventure part of the conversion report (the schema-2 writer and the registry entry are the lead's): what was
    detected and chosen, the runtime it runs on, and the pack. Native share 0: ScummVM interprets the game."""
    return {
        'kind': 'emulated',
        'native_share': 0.0,
        'engine': {'name': 'ScummVM', **runtime_identity},
        'game': {**export.candidate.as_dict(), 'choice': export.choice, 'candidates': export.candidates},
        'pack': {'files': export.files, 'data_bytes': export.data_bytes, 'id': export.game_id,
                 'datas': f'datas/games/{export.datas_name}-{export.game_id}', 'compression': 'none'},
        'executable': export.exe.name,
        'artwork': artwork or {},
    }
