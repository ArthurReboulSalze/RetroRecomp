"""WHDLoad installs: the slave's AmigaDOS hunk file, its `ws_` header and the install's layout (MIT).

Written from the public descriptions of the AmigaDOS hunk format and of the WHDLoad slave structure (whdload.de autodoc);
no WHDLoad code is used. The converter answers the slave's `resload_*` calls itself (`native/amiga_whdload/`), so it
only needs to know where the slave, its data folder and its disk images are, and what the header asks: memory sizes,
flags, and the Kickstart image of a KickEmu slave (the player's own, never shipped).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import posixpath
import re
import struct

from . import amiga_lha

FORMAT = 1

HUNK_HEADER, HUNK_CODE, HUNK_DATA, HUNK_BSS = 0x3F3, 0x3E9, 0x3EA, 0x3EB
HUNK_RELOC32, HUNK_SYMBOL, HUNK_DEBUG, HUNK_END = 0x3EC, 0x3F0, 0x3F1, 0x3F2
HUNK_DREL32, HUNK_RELOC32SHORT = 0x3F7, 0x3FC
MEM_CHIP, MEM_FAST = 1 << 30, 1 << 31

# ws_Flags bits (WHDLF_*), with the slave version that introduced each.
FLAGS = {0: 'Disk', 1: 'NoError', 2: 'EmulTrap', 3: 'NoDivZero', 4: 'Req68020', 5: 'ReqAGA', 6: 'NoKbd',
         7: 'EmulLineA', 8: 'EmulTrapV', 9: 'EmulChk', 10: 'EmulPriv', 11: 'EmulLineF', 12: 'ClearMem',
         13: 'Examine', 14: 'EmulDivZero', 15: 'EmulIllegal'}
SLAVE_ID = b'WHDLOADS'


class InstallError(ValueError):
    """A file or install the converter cannot use, with the reason."""


@dataclass
class Hunk:
    kind: str                     # 'code', 'data' or 'bss'
    memory: str                   # 'any', 'chip' or 'fast'
    size: int                     # bytes in memory
    data: bytes                   # initialised bytes (shorter than size for BSS tails)
    relocs: dict[int, list[int]] = field(default_factory=dict)   # target hunk -> offsets of 32-bit pointers


def _u32(blob: bytes, pos: int) -> int:
    if pos + 4 > len(blob):
        raise InstallError('hunk file ends early')
    return struct.unpack_from('>I', blob, pos)[0]


def hunks(blob: bytes) -> list[Hunk]:
    """The hunks of an AmigaDOS executable (code, data, BSS, 32-bit relocations; symbols and debug data skipped)."""
    if _u32(blob, 0) != HUNK_HEADER:
        raise InstallError('not an AmigaDOS executable')
    pos = 4
    while True:                                  # resident library names (none in practice)
        n = _u32(blob, pos)
        pos += 4
        if not n:
            break
        pos += 4 * n
    _table, first, last = (_u32(blob, pos + 4 * k) for k in range(3))
    pos += 12
    if last < first or last - first > 255:
        raise InstallError('bad hunk table')
    sizes = []
    for _ in range(last - first + 1):
        word = _u32(blob, pos)
        pos += 4
        if word & MEM_CHIP and word & MEM_FAST:   # extended memory attributes follow
            pos += 4
        sizes.append(word)
    out: list[Hunk] = []
    current: Hunk | None = None
    while pos < len(blob) and len(out) <= len(sizes):
        kind = _u32(blob, pos) & 0x3FFFFFFF
        pos += 4
        if kind in (HUNK_CODE, HUNK_DATA, HUNK_BSS):
            word = _u32(blob, pos)
            pos += 4
            longs = word & 0x3FFFFFFF
            index = len(out)
            if index >= len(sizes):
                raise InstallError('more hunks than the header declares')
            declared = sizes[index]
            memory = 'chip' if declared & MEM_CHIP and not declared & MEM_FAST else (
                'fast' if declared & MEM_FAST and not declared & MEM_CHIP else 'any')
            size = max(4 * (declared & 0x3FFFFFFF), 4 * longs)
            data = b'' if kind == HUNK_BSS else blob[pos:pos + 4 * longs]
            if kind != HUNK_BSS:
                if len(data) != 4 * longs:
                    raise InstallError('hunk data ends early')
                pos += 4 * longs
            current = Hunk({HUNK_CODE: 'code', HUNK_DATA: 'data', HUNK_BSS: 'bss'}[kind], memory, size, data)
            out.append(current)
        elif kind == HUNK_RELOC32:
            while True:
                n = _u32(blob, pos)
                pos += 4
                if not n:
                    break
                target = _u32(blob, pos)
                offsets = [_u32(blob, pos + 4 + 4 * k) for k in range(n)]
                pos += 4 + 4 * n
                if current is None:
                    raise InstallError('relocation before any hunk')
                current.relocs.setdefault(target, []).extend(offsets)
        elif kind in (HUNK_RELOC32SHORT, HUNK_DREL32):
            start = pos
            while True:
                if pos + 2 > len(blob):
                    raise InstallError('relocation ends early')
                n = struct.unpack_from('>H', blob, pos)[0]
                pos += 2
                if not n:
                    break
                target = struct.unpack_from('>H', blob, pos)[0]
                offsets = list(struct.unpack_from('>%dH' % n, blob, pos + 2))
                pos += 2 + 2 * n
                if current is None:
                    raise InstallError('relocation before any hunk')
                current.relocs.setdefault(target, []).extend(offsets)
            pos += (-(pos - start)) % 4
        elif kind == HUNK_SYMBOL:
            while True:
                n = _u32(blob, pos)
                pos += 4
                if not n:
                    break
                pos += 4 * (n & 0xFFFFFF) + 4
        elif kind == HUNK_DEBUG:
            pos += 4 + 4 * _u32(blob, pos)
        elif kind == HUNK_END:
            current = None
        else:
            raise InstallError('hunk type 0x%X is not read' % kind)
    if len(out) != len(sizes):
        raise InstallError('the file holds %d of its %d hunks' % (len(out), len(sizes)))
    for index, hunk in enumerate(out):
        for target, offsets in hunk.relocs.items():
            if target >= len(out) or any(o + 4 > hunk.size or o & 1 for o in offsets):
                raise InstallError('relocation outside its hunk in hunk %d' % index)
    return out


def relocate(loaded: list[Hunk], bases: list[int]) -> list[bytes]:
    """Each hunk's memory image once loaded at `bases`: data padded to its size, every pointer moved by its target base."""
    images = []
    for hunk in loaded:
        image = bytearray(hunk.size)
        image[:len(hunk.data)] = hunk.data
        for target, offsets in hunk.relocs.items():
            for o in offsets:
                value = (struct.unpack_from('>I', image, o)[0] + bases[target]) & 0xFFFFFFFF
                struct.pack_into('>I', image, o, value)
        images.append(bytes(image))
    return images


@dataclass(frozen=True)
class Slave:
    version: int
    flags: int
    base_mem: int                 # ws_BaseMemSize: chip memory the program gets, from address 0
    exec_install: int
    game_loader: int              # offset of the entry point in the slave
    current_dir: str              # data folder relative to the slave's folder, '' for the same folder
    dont_cache: int
    key_debug: int
    key_exit: int
    exp_mem: int                  # ws_ExpMem (v8): fast memory wanted, negative = optional, 0 = none
    name: str
    copy: str
    info: str
    kick_names: tuple[str, ...]   # ws_kickname (v16): accepted Kickstart image names, empty without KickEmu
    kick_size: int
    kick_crc: int
    config: str                   # ws_config (v17): the splash-window buttons, '' if none

    @property
    def flag_names(self) -> tuple[str, ...]:
        return tuple(name for bit, name in FLAGS.items() if self.flags & (1 << bit))

    @property
    def kickemu(self) -> bool:
        return bool(self.kick_size)


def _cstr(code: bytes, offset: int) -> str:
    if not offset or offset >= len(code):
        return ''
    end = code.find(b'\x00', offset)
    # WHDLoad texts use the byte -1 ($FF) as a line break.
    return code[offset:end if end >= 0 else len(code)].replace(b'\xff', b'\n').decode('latin-1')


def slave_header(loaded: list[Hunk]) -> Slave:
    """The `ws_` structure at the start of the slave's first hunk (only the fields its version defines)."""
    if not loaded or loaded[0].kind != 'code':
        raise InstallError('the slave does not start with a code hunk')
    code = loaded[0].data
    if len(code) < 32 or code[4:12] != SLAVE_ID:
        raise InstallError('not a WHDLoad slave (no WHDLOADS id)')
    version, flags, base_mem, exec_install, loader, current, dont_cache = struct.unpack_from('>HHIIHHH', code, 12)
    key_debug, key_exit = code[30], code[31]

    def field_at(fmt, pos, since):
        return struct.unpack_from(fmt, code, pos)[0] if version >= since and pos + struct.calcsize(fmt) <= len(code) else 0
    exp_mem = field_at('>i', 32, 8)
    name, copy, info = (_cstr(code, field_at('>H', p, 10)) for p in (36, 38, 40))
    kick_name, kick_size, kick_crc = field_at('>H', 42, 16), field_at('>I', 44, 16), field_at('>H', 48, 16)
    kicks: tuple[str, ...] = ()
    if kick_size and kick_name:
        if kick_crc == 0xFFFF:                    # a list of (crc.w, name rptr.w) pairs ending with crc 0
            pairs, pos = [], kick_name
            while pos + 4 <= len(code):
                crc, ptr = struct.unpack_from('>HH', code, pos)
                if not crc:
                    break
                pairs.append(_cstr(code, ptr))
                pos += 4
            kicks = tuple(pairs)
        else:
            kicks = (_cstr(code, kick_name),)
    config = _cstr(code, field_at('>H', 50, 17))
    return Slave(version, flags, base_mem, exec_install, loader, _cstr(code, current), dont_cache, key_debug, key_exit,
                 exp_mem, name, copy, info, kicks, kick_size, kick_crc, config)


_DISK = re.compile(r'(?i)^disk\.(\d+)$')


@dataclass(frozen=True)
class Install:
    slave_path: str               # member name of the chosen slave
    slave: Slave
    data_dir: str                 # folder of the data files inside the archive ('' = archive root)
    files: dict[str, amiga_lha.Member]        # data files by their path relative to data_dir (icons excluded)
    disks: dict[int, amiga_lha.Member]        # Disk.N images found in data_dir
    other_slaves: tuple[str, ...]


def _data_dir(listed: list[amiga_lha.Member], folder: str, current: str) -> str:
    """The archive folder the slave's ws_CurrentDir names, as stored in the archive.

    WHDLoad resolves ws_CurrentDir from the folder it was started in (the install's own folder), which is the slave's
    folder in most installs; some keep the slave inside its data folder. AmigaDOS names are case-insensitive, and a
    slave may carry a developer's absolute path ("SOURCES:…/data"): its last part is then tried. The first candidate
    that holds files wins; with none, the slave's folder. Icons' DATA tooltypes are not read yet."""
    names = [m.name for m in listed]

    def existing(path: str) -> str | None:
        path = posixpath.normpath(path) if path else ''
        path = '' if path == '.' else path
        if not path:
            return ''
        prefix = path.lower() + '/'
        return next((n[:len(prefix) - 1] for n in names if n.lower().startswith(prefix)), None)
    if not current:
        return folder
    rel = current.rstrip('/')
    if ':' in rel:
        rel = rel.rsplit('/', 1)[-1].rsplit(':', 1)[-1]
    root = folder.split('/', 1)[0] if folder else ''
    for base in dict.fromkeys((folder, posixpath.dirname(folder), root)):
        found = existing(posixpath.join(base, rel) if base else rel)
        if found is not None:
            return found
    return folder


_CUSTOM = re.compile(r'(?i)^CUSTOM([1-5])=\s*(\$[0-9a-f]+|0x[0-9a-f]+|-?\d+)\s*$')


def icon_strings(data: bytes) -> list[str]:
    """The strings of an icon (.info) file: its default tool and its ToolTypes, which icon.library's DiskObject layout
    stores each as a 32-bit length followed by the bytes, the last one NUL. Found by that framing; nothing is run."""
    strings, i, n = [], 0, len(data)
    while i + 5 <= n:
        length = int.from_bytes(data[i:i + 4], 'big')
        end = i + 4 + length
        if 2 <= length <= 256 and end <= n and data[end - 1] == 0:
            text = data[i + 4:end - 1]
            if all(32 <= c < 127 or c >= 160 for c in text):
                strings.append(text.decode('latin-1'))
                i = end
                continue
        i += 1
    return strings


def custom_options(blob: bytes, chosen: 'Install') -> tuple[int, int, int, int, int]:
    """CUSTOM1..5 as the install's own icon sets them: WHDLoad reads the ToolTypes of the icon it is started from, the
    slave's icon beside it (`<slave>.info`), and gives them to the slave through resload_Control. A ToolType in
    parentheses is switched off, as on the Workbench; a value is decimal, or hexadecimal written $10 or 0x10."""
    name = chosen.slave_path.rsplit('.', 1)[0].lower() + '.info'
    icon = next((m for m in amiga_lha.members(blob) if m.name.lower() == name), None)
    values = [0] * 5
    if icon is not None:
        for text in icon_strings(amiga_lha.extract(blob, icon)):
            match = _CUSTOM.match(text.strip())
            if match:
                raw = match.group(2)
                number = int(raw[1:], 16) if raw.startswith('$') else int(raw, 16) if raw.lower().startswith('0x') else int(raw)
                values[int(match.group(1)) - 1] = number & 0xFFFFFFFF
    return tuple(values)


def install(blob: bytes, choose: str | None = None) -> Install:
    """Describe a WHDLoad install archive. With several slaves, `choose` names the one to use (else it is refused)."""
    listed = amiga_lha.members(blob)
    slaves = [m for m in listed if m.name.lower().endswith('.slave')]
    if not slaves:
        raise InstallError('no WHDLoad slave in this archive')
    if choose is not None:
        chosen = [m for m in slaves if m.name == choose]
    else:
        chosen = slaves if len(slaves) == 1 else []
    if len(chosen) != 1:
        raise InstallError('choose one slave: ' + ', '.join(m.name for m in slaves))
    member = chosen[0]
    slave = slave_header(hunks(amiga_lha.extract(blob, member)))
    folder = posixpath.dirname(member.name)
    data_dir = _data_dir(listed, folder, slave.current_dir)
    prefix = (data_dir + '/' if data_dir else '').lower()
    files, disks = {}, {}
    for m in listed:
        if m is member or not m.name.lower().startswith(prefix) or m.name.endswith('/'):
            continue
        rel = m.name[len(prefix):]
        if rel.lower().endswith('.info') and '/' not in rel:
            continue
        files[rel] = m
        match = _DISK.match(rel)
        if match:
            disks[int(match.group(1))] = m
    return Install(member.name, slave, data_dir, files, disks, tuple(m.name for m in slaves if m is not member))
