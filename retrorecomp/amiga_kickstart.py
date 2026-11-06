"""The player's own Amiga Kickstart: recognise it, normalise it in memory, say which installs it unlocks (MIT).

Some WHDLoad installs ask for a Kickstart image (header fields `ws_kickname`, `ws_kicksize`, `ws_kickcrc`, or a call to
`resload_LoadKick`). The image is the player's own file: it is read in place, normalised in memory, hashed, and never copied,
stored in the library or shared. Nothing here carries Commodore code; the tests write small authored images of their own.

* `normalise` accepts what players actually have: the plain 256 / 512 KiB image, a 256 KiB image doubled in a 512 KiB file, a
  byte-swapped dump (the bytes of each pair exchanged), and an Amiga Forever (Cloanto) file (11-byte `AMIROMTYPE1` tag, then
  the image XOR-ed with the repeating `rom.key` kept beside it). A Kickstart of the 1.x to 3.x generation starts with a
  `$1111` or `$1114` word followed by a `jmp` (`$4EF9`); that is how a candidate is recognised, never by its name.
* `KNOWN` names the versions by (size, CRC-32), the public identifier of these ROMs, as listed in vAmiga's ROM database
  (facts only). A version name is a label: the identity of an image is the SHA-256 of its normalised bytes.
* A slave's request is matched with (size, CRC-16): the checksum WHDLoad's `ws_kickcrc` and `resload_CRC16` use, which is
  the CRC-16 of `amiga_lha` (one implementation, reused). The CRC-16 of the images of the real Kickstarts was not checked
  here (no image was read); the match is by the same function the slave headers were written with.
* `scan` / `identify` read a file or, non-recursively, a folder; `match` picks the image a request accepts;
  `path_needs_kickstart` and `kickstart_request` read an install's slave header only; `validate_kickstarts` is the text the
  Options window's Check button shows; `require` is the check made before a conversion starts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import struct
import zlib

from . import amiga_lha

FORMAT = 1
SIZES = (256 * 1024, 512 * 1024)
CLOANTO_TAG = b'AMIROMTYPE1'
KEY_FILE = 'rom.key'
CANDIDATE_SIZES = frozenset(SIZES + tuple(size + len(CLOANTO_TAG) for size in SIZES))
MAX_FOLDER_CANDIDATES = 200
# The names of the normalisations a record can carry (they enter the conversion report).
CLOANTO, SWAPPED, UNDOUBLED = 'cloanto-decrypted', 'byte-swapped', 'undoubled'

# Versions the installs ask for, by (size, CRC-32). CRC-32 values and revisions are those of vAmiga's ROM database
# (Core/rvlib/Roms/RomTypes.h, RomsAmiga.cpp), read as facts. `name` is the WHDLoad image name (WHDLoad's documentation and
# the slave headers of the library). Not verified: the `model` labels. vAmiga lists 33.180 and 34.005 with no model and 40.063
# as "A500"; 'A500' for the first two follows the WHDLoad names (`kick33180.A500`, `kick34005.A500`), and 'A600/A2000' for
# 40.063 follows `kick40063.A600` and the brief of the maintainer, not vAmiga. Left out: values not found in that database
# (for instance any SHA-256 table, and the A3000 build of 1.3, `$E0F37258`, which is another image).
KNOWN = {
    (262144, 0xA6CE1636): {'version': '33.180', 'os': '1.2', 'model': 'A500', 'name': 'kick33180.A500'},
    (262144, 0xC4F0F55F): {'version': '34.005', 'os': '1.3', 'model': 'A500', 'name': 'kick34005.A500'},
    (524288, 0xFC24AE0D): {'version': '40.063', 'os': '3.1', 'model': 'A500/A600/A2000', 'name': 'kick40063.A600'},
    (524288, 0x1483A091): {'version': '40.068', 'os': '3.1', 'model': 'A1200', 'name': 'kick40068.A1200'},
    (524288, 0xD6BAE334): {'version': '40.068', 'os': '3.1', 'model': 'A4000', 'name': 'kick40068.A4000'},
}


class KickstartError(ValueError):
    """A file that is no usable Kickstart. `code` is the suffix of the interface string that says why
    (`amiga_kickstart_<code>`), `params` its values."""

    def __init__(self, code: str, **params):
        self.code, self.params = code, params
        super().__init__(f'{code}: {params}' if params else code)


# The WHDLoad CRC-16 (`ws_kickcrc`, `resload_CRC16`) is the LHA one: reused, not copied.
crc16 = amiga_lha.crc16


def _is_kickstart_start(data: bytes) -> bool:
    """A 1.x / 2.x / 3.x Kickstart starts `$1111` or `$1114`, then `jmp` (`$4EF9`)."""
    return len(data) >= 4 and data[0] == 0x11 and data[1] in (0x11, 0x14) and data[2] == 0x4E and data[3] == 0xF9


def _swap_pairs(data: bytes) -> bytes:
    swapped = bytearray(len(data))
    swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
    return bytes(swapped)


def _xor_key(body: bytes, key: bytes) -> bytes:
    stream = (key * (len(body) // len(key) + 1))[:len(body)]
    return (int.from_bytes(body, 'big') ^ int.from_bytes(stream, 'big')).to_bytes(len(body), 'big')


def normalise(data: bytes, key: bytes | None = None) -> tuple[bytes, list[str]]:
    """The plain image of a Kickstart file and the list of what was undone to get it (`CLOANTO`, `SWAPPED`, `UNDOUBLED`).

    `key` is the content of the `rom.key` of an Amiga Forever file. Raises `KickstartError` (`cloanto_key_missing`,
    `cloanto_key_wrong`, `not_kickstart`). Nothing is written."""
    data = bytes(data)
    done: list[str] = []
    encrypted = data[:len(CLOANTO_TAG)] == CLOANTO_TAG and len(data) - len(CLOANTO_TAG) in SIZES
    if encrypted:
        if not key:
            raise KickstartError('cloanto_key_missing')
        data = _xor_key(data[len(CLOANTO_TAG):], key)
        done.append(CLOANTO)
    if len(data) not in SIZES:
        raise KickstartError('not_kickstart', size=len(data))
    if not _is_kickstart_start(data):
        if _is_kickstart_start(_swap_pairs(data[:4])):
            data = _swap_pairs(data)
            done.append(SWAPPED)
        elif encrypted:
            raise KickstartError('cloanto_key_wrong')
        else:
            raise KickstartError('not_kickstart', size=len(data))
    half = SIZES[0]
    if len(data) == SIZES[1] and data[:half] == data[half:]:
        data = data[:half]
        done.append(UNDOUBLED)
    return data, done


@dataclass(frozen=True)
class Kickstart:
    """A Kickstart found in the player's files. `size`, `sha256`, `crc32` and `crc16` describe the normalised image."""
    path: Path
    file_name: str
    size: int
    sha256: str
    crc32: int
    crc16: int
    version: dict | None          # an entry of KNOWN (a copy), or None when the version is not one the installs ask for
    normalisations: tuple[str, ...]

    def label(self) -> str:
        return describe(self.version, self.size) if self.version else f'{self.size // 1024} KiB'


@dataclass(frozen=True)
class Rejected:
    """A candidate file that is no Kickstart, with the reason (`code` and `params` as in `KickstartError`)."""
    path: Path
    file_name: str
    code: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Scan:
    records: tuple[Kickstart, ...]
    rejected: tuple[Rejected, ...]


def describe(info: dict, size: int) -> str:
    """`1.3 (34.005, 256 KiB, A500)`: the language-free label of a known version."""
    return f"{info['os']} ({info['version']}, {size // 1024} KiB, {info['model']})"


def _key_beside(folder: Path) -> bytes | None:
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name.lower() == KEY_FILE and entry.is_file() and entry.stat().st_size <= 1 << 20:
                    return Path(entry.path).read_bytes() or None
    except OSError:
        pass
    return None


def _record(path: Path, data: bytes, key: bytes | None) -> Kickstart:
    image, done = normalise(data, key)
    crc32 = zlib.crc32(image) & 0xFFFFFFFF
    known = KNOWN.get((len(image), crc32))
    return Kickstart(path, path.name, len(image), hashlib.sha256(image).hexdigest(), crc32, crc16(image),
                     dict(known) if known else None, tuple(done))


def _read_candidate(path: Path, key: bytes | None, key_folder: Path) -> Kickstart | Rejected:
    try:
        size = path.stat().st_size
        if size not in CANDIDATE_SIZES:
            return Rejected(path, path.name, 'not_kickstart', {'size': size})
        data = path.read_bytes()
        if key is None and data[:len(CLOANTO_TAG)] == CLOANTO_TAG:
            key = _key_beside(key_folder)
        return _record(path, data, key)
    except KickstartError as error:
        return Rejected(path, path.name, error.code, {k: v for k, v in error.params.items()})
    except OSError as error:
        return Rejected(path, path.name, 'unreadable', {'error': str(error)})


def scan(path) -> Scan:
    """The Kickstarts at `path`: one file, or the files of a folder (not recursive). Every candidate is identified by its
    content, never by its name. A single file that is no Kickstart is reported with its reason. In a folder, only files whose
    size a Kickstart can have are candidates (the others are not mentioned). Raises OSError when `path` cannot be read."""
    path = Path(path)
    if path.is_dir():
        key = _key_beside(path)
        found, refused = [], []
        with os.scandir(path) as entries:
            names = sorted((e for e in entries if e.is_file()), key=lambda e: e.name.lower())
        for entry in names:
            if entry.name.lower() == KEY_FILE:
                continue
            if entry.stat().st_size not in CANDIDATE_SIZES:
                continue
            if len(found) + len(refused) >= MAX_FOLDER_CANDIDATES:
                break
            item = _read_candidate(Path(entry.path), key, path)
            (found if isinstance(item, Kickstart) else refused).append(item)
        return Scan(tuple(found), tuple(refused))
    if not path.is_file():
        raise FileNotFoundError(str(path))
    item = _read_candidate(path, None, path.parent)
    return Scan((item,), ()) if isinstance(item, Kickstart) else Scan((), (item,))


def identify(path) -> list[Kickstart]:
    """The Kickstart records at `path` (see `scan` for the files that were refused and why)."""
    return list(scan(path).records)


def read_image(record: Kickstart) -> bytes:
    """The normalised image of a record, read again from the player's file and checked against the record's SHA-256."""
    key = _key_beside(record.path.parent) if CLOANTO in record.normalisations else None
    image, _ = normalise(record.path.read_bytes(), key)
    if hashlib.sha256(image).hexdigest() != record.sha256:
        raise KickstartError('not_kickstart', size=len(image))
    return image


def match(records, size: int, crc: int) -> Kickstart | None:
    """The first record a request for (`ws_kicksize`, CRC-16) accepts, or None."""
    return next((r for r in records if r.size == size and r.crc16 == crc), None)


# --- what an install asks for (the slave header only: nothing of the game is decompressed besides the slave) ----------

LOADKICK_OFFSET = 0x68          # resload_LoadKick, in the jump table the slave gets in A5
_JSR_OR_JMP_D16 = frozenset(range(0x4EA8, 0x4EB0)) | frozenset(range(0x4EE8, 0x4EF0))   # jsr / jmp d16(An)
MIN_LOADKICK_VERSION = 11       # resload_LoadKick exists from this ws_Version


@dataclass(frozen=True)
class Request:
    """What an install's slave asks of the Kickstart. `accepted` lists the images its header accepts, in the slave's order:
    {'name', 'size', 'crc16'}; it is empty for a slave that only calls `resload_LoadKick`. `mode` is 'header',
    'resload_LoadKick' or 'both'."""
    title: str
    mode: str
    accepted: tuple[dict, ...]
    ws_version: int


def _header_entries(code: bytes, slave) -> tuple[dict, ...]:
    if not slave.kick_size:
        return ()
    if slave.kick_crc != 0xFFFF:
        return ({'name': slave.kick_names[0] if slave.kick_names else '', 'size': slave.kick_size,
                 'crc16': slave.kick_crc},)
    pairs, pos = [], struct.unpack_from('>H', code, 42)[0]
    while pos + 4 <= len(code):
        crc, pointer = struct.unpack_from('>HH', code, pos)
        if not crc:
            break
        end = code.find(b'\x00', pointer) if pointer < len(code) else -1
        name = code[pointer:end if end >= 0 else len(code)].decode('latin-1') if pointer else ''
        pairs.append({'name': name, 'size': slave.kick_size, 'crc16': crc})
        pos += 4
    return tuple(pairs)


def _calls_loadkick(loaded) -> bool:
    for hunk in loaded:
        if hunk.kind != 'code':
            continue
        code = hunk.data
        for pos in range(0, len(code) - 3, 2):
            if (code[pos] << 8 | code[pos + 1]) in _JSR_OR_JMP_D16 and code[pos + 2] == 0 and code[pos + 3] == LOADKICK_OFFSET:
                return True
    return False


def request_of_slave(blob: bytes) -> Request:
    """The request of a slave given as the bytes of its hunk file. Raises `amiga_whdload.InstallError` when it is no slave."""
    from . import amiga_whdload
    loaded = amiga_whdload.hunks(blob)
    slave = amiga_whdload.slave_header(loaded)
    accepted = _header_entries(loaded[0].data, slave)
    by_call = slave.version >= MIN_LOADKICK_VERSION and _calls_loadkick(loaded)
    mode = 'both' if accepted and by_call else 'header' if accepted else 'resload_LoadKick' if by_call else ''
    return Request((slave.name.split('\n', 1)[0].strip()), mode, accepted, slave.version)


def kickstart_request(path) -> Request | None:
    """The Kickstart an install asks for, or None when it asks for none (or is no single-slave WHDLoad install). Only the
    archive's headers and its slave are read; every failure means None, as `cps1_qsound.path_needs_dsp_rom`."""
    from . import amiga
    path = Path(path)
    try:
        member = amiga.slave_member(path)
        if member is None or path.stat().st_size > amiga.MAX_ARCHIVE_BYTES:
            return None
        blob = path.read_bytes()
        listed = next(m for m in amiga_lha.members(blob) if m.name == member)
        request = request_of_slave(amiga_lha.extract(blob, listed))
    except (OSError, ValueError, StopIteration):
        return None
    return request if request.mode else None


def path_needs_kickstart(path) -> bool:
    """Whether the install at `path` asks for a Kickstart: a `ws_kicksize` in its header, or a `jsr`/`jmp d16(An)` with
    d16 = $68 (`resload_LoadKick`) in a slave of `ws_Version` 11 or more. A static answer, not a claim that it runs."""
    return kickstart_request(path) is not None


def request_for(entries, records):
    """The first (entry, record) pair of a request's `accepted` list that the player's records satisfy, or None."""
    for entry in entries:
        hit = match(records, entry['size'], entry['crc16'])
        if hit is not None:
            return entry, hit
    return None


def _entry_label(entry: dict) -> str:
    key = entry['name'].lower().removeprefix('kick')
    for (size, _), info in KNOWN.items():
        if size == entry['size'] and info['name'].lower().removeprefix('kick') == key:
            return f"{info['os']} ({info['version']}, {size // 1024} KiB, {info['name']})"
    return f"{entry['name'] or '?'} ({entry['size'] // 1024} KiB)"


# --- texts (interface strings: amiga_kickstart_*) ---------------------------------------------------------------------

def _tr(language: str, key: str, **values) -> str:
    from .i18n import tr
    return tr('amiga_kickstart_' + key, language, **values)


def _reason_text(language: str, item: Rejected) -> str:
    if item.code == 'unreadable':
        return _tr(language, 'invalid', error=item.params.get('error', ''))
    return _tr(language, item.code, name=item.file_name, **item.params)


def validate_kickstarts(path, language: str = 'en') -> str:
    """The text of the Check button: what the file or folder holds, in the interface language. Never raises for a content
    problem; a path that cannot be read says so with `amiga_kickstart_invalid`."""
    try:
        result = scan(path)
    except OSError as error:
        return _tr(language, 'invalid', error=str(error))
    lines = []
    if result.records:
        found = {r.sha256: r for r in result.records if r.version}
        labels = [r.label() for r in found.values()]
        wanted = [describe(info, size) for (size, _), info in KNOWN.items()]
        missing = [label for label in wanted if label not in labels] or ['–']
        if labels:
            lines.append(_tr(language, 'valid', found='; '.join(dict.fromkeys(labels)), missing='; '.join(missing)))
        lines += [_tr(language, 'unknown_version', name=r.file_name) for r in result.records if not r.version][:3]
    lines += [_reason_text(language, item) for item in result.rejected][:3]
    return '\n'.join(lines) or _tr(language, 'none_found', name=Path(path).name)


def blocked_message(request: Request, language: str = 'en') -> str:
    """The sentence that stops a conversion whose install asks for a Kickstart the player did not provide."""
    if not request.accepted:
        return _tr(language, 'required_unnamed', game=request.title)
    return _tr(language, 'required', game=request.title, wanted=' / '.join(_entry_label(e) for e in request.accepted))


def require(option, install_path, language: str = 'en') -> Kickstart | None:
    """The check made before a conversion starts. Returns None when the install at `install_path` asks for no Kickstart,
    else the record the player's file or folder (`option`, as saved in the preferences) gives it; raises ValueError with
    the blocked message when none is selected or none of the player's images is accepted. A request that only calls
    `resload_LoadKick` is matched when the player has any recognised Kickstart (the exact image is checked at run time)."""
    request = kickstart_request(install_path)
    if request is None:
        return None
    from .paths import selected_bios_path
    chosen = selected_bios_path(option)
    records = []
    if chosen is not None:
        try:
            records = identify(chosen)
        except OSError:
            records = []
    if not request.accepted:
        known = [r for r in records if r.version]
        if known:
            return known[0]
    else:
        hit = request_for(request.accepted, records)
        if hit is not None:
            return hit[1]
    raise ValueError(blocked_message(request, language))
