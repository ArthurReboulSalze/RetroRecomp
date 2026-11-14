"""The root directory of an Atari ST floppy (MIT): what the desktop shows of disk 1, read from the image without running it.

A game whose boot reaches the GEM desktop waits there for its program to be opened, as on the real machine. When the root of
disk 1 holds exactly one program the player would open (a .PRG, .APP, .GTP or .TOS file that is not hidden and is not a
hard-disk installer, whose names start with INSTAL), the conversion asks the desktop to start it by the TOS's own autostart
line (#Z), which Hatari serves in a desktop file of its own in memory (its inffile.c): the disk image is never changed.
A disk with an AUTO folder starts its own programs and gets no autostart. TOS 1.00 and 1.02 have no autostart line.

When disk 1 holds several programs, one is chosen only where a clear rule picks it, never by a guess: the one program whose name is
a word of the game's title (CRICKET.PRG for "Championship Cricket"), or else the one program that is not a utility by a short list
of names (setup, configuration, formatter, reader, backup, unpacker). Two programs that fit, or none, leave the choice to the
player, who opens the program at the desktop; the report says so (`desktop_autostart`).

The disk order is read from the image names (disk_order_key): the boot disk first, then "Disk 1/2/3", "Disk A/B", "Side A/B",
"Reel 1/2", "Volume I/II", then the disks that only have a name; so disk 1 is the one the machine boots from.

The images are read as the TOS would read them: the sectors of IPF (from the IPF records: INFO, IMGE and DATA, and the data
elements of each block, the layout Clock Signal's MIT reader and MAME's BSD-3 reader follow), ST (raw sectors) and MSA
(run-length tracks). STX images are not read here (no autostart for them).
"""
from __future__ import annotations

import re
import struct

PROGRAM_EXTENSIONS = ('PRG', 'APP', 'GTP', 'TOS')
INSTALLER_PREFIX = 'INSTAL'
MAX_SECTORS = 3000


# Utilities that are not the game: a program whose name (letters and digits only) is one of these words, or starts with one of the
# prefixes, is not chosen by the "only program that is not a utility" rule.
UTILITY_WORDS = frozenset({'SETUP', 'CONFIG', 'CONFIGUR', 'CONFIGURE', 'FORMAT', 'README', 'READ', 'READER', 'VIEW', 'VIEWER', 'HELP',
                           'MANUAL', 'DOC', 'DOCS', 'UNPACK', 'DEPACK', 'UNZIP', 'BACKUP', 'COPY', 'COPIER', 'UTIL', 'UTILS',
                           'UTILITY', 'HDINST', 'MUSIC', 'EDITOR'})
UTILITY_PREFIXES = ('INSTAL', 'FORMAT', 'BACKUP', 'README', 'UNPACK', 'DEPACK', 'SETUP')
TITLE_STOP_WORDS = frozenset({'THE', 'AND', 'FOR', 'FROM', 'WITH', 'LES', 'DES', 'UND', 'DER', 'DIE', 'DAS', 'EDITION', 'GAME'})
MIN_TITLE_WORD = 4


class DiskError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------------------- disk order
_TAG = re.compile(r'[\(\[]([^\)\]]*)[\)\]]')
_ORDINAL = re.compile(r'(?<![a-z])(disk|disc|side|reel|tape|part|volume|vol)(?![a-z])\.?[\s_.-]?(\d{1,2}|[ivx]{1,4}|[a-z])(?![a-z0-9])', re.I)
_BOOT_WORD = re.compile(r'(?<![a-z])(boot|startup|start[\s_-]?up|start|program|main|loader)(?![a-z])', re.I)
_DISK_WORD = re.compile(r'(?<![a-z])(disk|disc|side|reel|tape|part|volume|vol)(?![a-z])', re.I)
_TRAILING = re.compile(r'[\s_.-]((?:\d{1,2})|[a-z])$', re.I)
_ROMAN = {'I': 1, 'V': 5, 'X': 10}


def _ordinal(word: str, token: str) -> int:
    token = token.upper()
    if token.isdigit():
        return int(token)
    if len(token) == 1 and not (word.lower().startswith('vol') and token in _ROMAN):
        return ord(token) - 64                          # Disk A = 1, Disk B = 2
    total = 0                                           # a Roman numeral (Volume II), subtractive notation
    for index, ch in enumerate(token):
        value = _ROMAN.get(ch, 0)
        total += -value if index + 1 < len(token) and _ROMAN.get(token[index + 1], 0) > value else value
    return total


def disk_order_key(name: str) -> tuple:
    """How a disk image's name places it in its game's set, the order the player's disk drive is fed in: first the disk without
    a label and the boot disks (Boot, StartUp, Program, Main, Loader), then the numbered ones (Disk 1, Disk A, Side B, Reel 2,
    Volume II: by the number or letter, so Disk 10 follows Disk 9), then the disks that only have a name (Games Disk, Animation
    Disk), and the file name breaks ties. The labels are read from the bracketed tags of preservation sets
    ("Game (Europe) (Disk 2).ipf") and, in a name without tags, from the end of the stem ("game 2.st", "game_b.st")."""
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    tags = _TAG.findall(stem)
    boot = False
    ordinal = 0
    labelled = False
    for tag in tags:
        if _BOOT_WORD.search(tag):
            boot = True
        found = _ORDINAL.search(tag)
        if found:
            ordinal = _ordinal(found.group(1), found.group(2))
        if _DISK_WORD.search(tag) or _BOOT_WORD.search(tag):
            labelled = True
    if not tags:
        found = _ORDINAL.search(stem) or _TRAILING.search(stem)
        if found:
            ordinal = _ordinal('disk', found.group(found.lastindex))
            labelled = True
    if boot or not labelled:
        group = 0
    elif ordinal:
        group = 1
    else:
        group = 2
    return group, ordinal, name.casefold(), name


def order_disks(names) -> list[str]:
    return sorted(names, key=disk_order_key)


# ------------------------------------------------------------------------------------------------------------- IPF
def _ipf_records(blob: bytes):
    pos = 0
    while pos + 12 <= len(blob):
        kind, length, _crc = struct.unpack('>4sII', blob[pos:pos + 12])
        if length < 12:
            raise DiskError('IPF: invalid record')
        yield pos, kind, length
        if kind == b'DATA':
            if pos + 16 > len(blob):
                raise DiskError('IPF: truncated record')
            length += struct.unpack('>I', blob[pos + 12:pos + 16])[0]
        pos += length


def _mfm_byte(cells: int) -> int:
    value = 0
    for bit in range(8):
        value = (value << 1) | ((cells >> (14 - 2 * bit)) & 1)
    return value


def _ipf_stream(blob: bytes, data: int, block_count: int) -> list[tuple[int, bool]]:
    """The bytes of a track's blocks in order, each with True when it is an A1 sync mark (MFM cells 4489)."""
    stream: list[tuple[int, bool]] = []
    for b in range(block_count):
        if data + 32 * (b + 1) > len(blob):
            raise DiskError('IPF: truncated block descriptor')
        f = struct.unpack('>8I', blob[data + 32 * b:data + 32 * b + 32])
        flags, offset = f[5], f[7]
        if not offset:
            continue
        p = data + offset
        while p < len(blob) and blob[p]:
            header = blob[p]
            p += 1
            width, n = header >> 5, 0
            for _ in range(width):
                if p >= len(blob):
                    raise DiskError('IPF: truncated element')
                n = (n << 8) | blob[p]
                p += 1
            bits = n if flags & 4 else n * 8
            size = (bits + 7) // 8
            chunk = blob[p:p + size]
            p += size
            kind = header & 0x1f
            if kind in (2, 3):                          # data, gap: plain bytes
                stream.extend((c, False) for c in chunk)
            elif kind in (1, 4):                        # sync, raw: MFM cells, two bytes a byte
                for i in range(0, len(chunk) - 1, 2):
                    cells = (chunk[i] << 8) | chunk[i + 1]
                    stream.append((_mfm_byte(cells), cells == 0x4489))
            elif kind == 5:                             # fuzzy: unknown bytes
                stream.extend((0, False) for _ in range(size))
            if len(stream) > 64 * 1024:
                raise DiskError('IPF: track too long')
    return stream


def _track_sectors(stream, out: dict, cylinder: int, head: int) -> None:
    current = None
    i = 0
    while i < len(stream):
        value, mark = stream[i]
        if not (mark and value == 0xA1):
            i += 1
            continue
        j = i
        while j < len(stream) and stream[j][1] and stream[j][0] == 0xA1:
            j += 1
        if j >= len(stream):
            break
        tag = stream[j][0]
        if tag == 0xFE and j + 4 < len(stream):
            current = tuple(v for v, _ in stream[j + 1:j + 5])
        elif tag in (0xFB, 0xF8) and current is not None:
            size = 128 << (current[3] & 3)
            if current[0] == cylinder and current[1] == head and j + size < len(stream):
                out.setdefault((cylinder, head, current[2]), bytes(v for v, _ in stream[j + 1:j + 1 + size]))
            current = None
        i = j
    return None


def ipf_sectors(blob: bytes, cylinders: int = 2) -> dict:
    """The standard-format sectors of the first `cylinders` cylinders (the desktop rules need two; `logical_content` asks for all of them)."""
    tracks, keys = {}, {}
    if blob[:4] != b'CAPS':
        raise DiskError('not an IPF image')
    for pos, kind, _length in _ipf_records(blob):
        if kind == b'IMGE':
            f = struct.unpack('>20I', blob[pos + 12:pos + 92])
            tracks[(f[0], f[1])] = {'blocks': f[10], 'key': f[13]}
            keys[f[13]] = (f[0], f[1])
        elif kind == b'DATA':
            key = struct.unpack('>I', blob[pos + 24:pos + 28])[0]
            if key in keys:
                tracks[keys[key]]['data'] = pos + 28
    out: dict = {}
    for (cylinder, head), track in sorted(tracks.items()):
        if 'data' in track and cylinder < cylinders:          # the boot sector, the FATs and the root are on the first two cylinders
            _track_sectors(_ipf_stream(blob, track['data'], track['blocks']), out, cylinder, head)
    return out


# ----------------------------------------------------------------------------------------------------------- ST, MSA
def _geometry(boot: bytes) -> tuple[int, int]:
    spt, heads = struct.unpack('<HH', boot[24:28])
    if not (8 <= spt <= 12 and heads in (1, 2)):
        raise DiskError('no DOS geometry')
    return spt, heads


def st_sectors(blob: bytes) -> dict:
    if len(blob) < 512 or len(blob) % 512:
        raise DiskError('not an ST image')
    spt, heads = _geometry(blob[:512])
    out = {}
    for lsn in range(min(len(blob) // 512, MAX_SECTORS)):
        track, sector = divmod(lsn, spt)
        out[(track // heads, track % heads, sector + 1)] = blob[lsn * 512:(lsn + 1) * 512]
    return out


def msa_sectors(blob: bytes) -> dict:
    if len(blob) < 10 or blob[:2] != b'\x0e\x0f':
        raise DiskError('not an MSA image')
    spt, sides, first, last = struct.unpack('>HHHH', blob[2:10])
    if not (8 <= spt <= 12 and sides in (0, 1) and first <= last <= 85):
        raise DiskError('MSA: invalid header')
    track_size = spt * 512
    pos, out = 10, {}
    for track in range(first, last + 1):
        for side in range(sides + 1):
            if pos + 2 > len(blob):
                raise DiskError('MSA: truncated')
            length = struct.unpack('>H', blob[pos:pos + 2])[0]
            data = blob[pos + 2:pos + 2 + length]
            pos += 2 + length
            if length != track_size:                    # run-length: E5 byte count
                plain, i = bytearray(), 0
                while i < len(data) and len(plain) < track_size:
                    if data[i] == 0xE5 and i + 3 < len(data):
                        plain += bytes([data[i + 1]]) * struct.unpack('>H', data[i + 2:i + 4])[0]
                        i += 4
                    else:
                        plain.append(data[i])
                        i += 1
                data = bytes(plain[:track_size])
            if len(data) != track_size:
                raise DiskError('MSA: invalid track')
            for s in range(spt):
                out[(track, side, s + 1)] = data[s * 512:(s + 1) * 512]
    return out


# -------------------------------------------------------------------------------------------------- the root directory
def root_entries(sectors: dict) -> list[dict]:
    """The entries of the root directory (name, extension, attributes, size), as the TOS reads them from the boot sector's BPB.

    The TOS always takes a floppy to have two FATs, whatever the BPB's number of FATs says (its BIOS puts the root directory at the reserved sectors
    plus two FATs): a disk that declares one is read there too (Battle Probe, Pharaoh III and Trailblazer of the 275 tried: with the field believed,
    their root looked empty while the TOS lists their programs)."""
    boot = sectors.get((0, 0, 1))
    if not boot or len(boot) != 512:
        raise DiskError('no boot sector')
    bps, spc, reserved, fats, entries = struct.unpack('<HBHBH', boot[11:19])
    per_fat = struct.unpack('<H', boot[22:24])[0]
    spt, heads = _geometry(boot)
    if bps != 512 or not spc or not reserved or fats not in (1, 2) or not 16 <= entries <= 512 or not 1 <= per_fat <= 12:
        raise DiskError('no DOS file system')
    first = reserved + 2 * per_fat
    out = []
    for n in range((entries * 32 + 511) // 512):
        track, sector = divmod(first + n, spt)
        data = sectors.get((track // heads, track % heads, sector + 1))
        if data is None:
            raise DiskError('a root directory sector is missing')
        for e in range(16):
            entry = data[e * 32:(e + 1) * 32]
            if entry[0] == 0:
                return out
            if entry[0] == 0xE5:
                continue
            out.append({'name': entry[:8].decode('latin-1').rstrip(), 'ext': entry[8:11].decode('latin-1').rstrip(),
                        'attr': entry[11], 'size': struct.unpack('<I', entry[28:32])[0]})
    return out


def logical_content(blob: bytes, extension: str) -> bytes:
    """The standard-format sectors of a whole disk image, one after the other in (cylinder, side, sector) order: what a TOS or a loader reads from a disk, and so what a program
    loaded from it is made of (a program that is relocated or unpacked on loading no longer matches it). A track written in a custom format has no standard sector and
    adds nothing; an image this module cannot read (STX) has no content. Used to tie observed instructions to the player's own disks (`atarist_knowledge`)."""
    extension = extension.lower().lstrip('.')
    try:
        sectors = ipf_sectors(blob, 1 << 16) if extension == 'ipf' else read_sectors(blob, extension)
    except DiskError:
        return b''
    return b''.join(data for _, data in sorted(sectors.items()))


def read_sectors(blob: bytes, extension: str) -> dict:
    extension = extension.lower().lstrip('.')
    if extension == 'ipf':
        return ipf_sectors(blob)
    if extension == 'st':
        return st_sectors(blob)
    if extension == 'msa':
        return msa_sectors(blob)
    raise DiskError(f'{extension.upper()} images are not read for the desktop')


def _squash(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def is_utility(name: str) -> bool:
    """True for a program name that is a utility and not the game (the short list of UTILITY_WORDS and UTILITY_PREFIXES)."""
    word = _squash(name)
    return word in UTILITY_WORDS or word.startswith(UTILITY_PREFIXES)


def title_words(title: str) -> set[str]:
    """The words of a game's title a program name can be compared with: letters and digits, at least MIN_TITLE_WORD long, no Roman
    numeral and no article or preposition."""
    words = {w.upper() for w in re.findall(r'[A-Za-z0-9]+', title)}
    return {w for w in words if len(w) >= MIN_TITLE_WORD and w not in TITLE_STOP_WORDS and not re.fullmatch(r'[IVX]+', w)}


def autostart_decision(blob: bytes, extension: str, title: str = '') -> dict:
    """What the desktop should start from disk 1: {'program': 'A:\\NAME.PRG' or None, 'candidates': the programs of the root
    ('NAME.PRG'), 'rule': which rule chose or None, 'reason': why}. One program: that one. Several: the one whose name is a
    word of the title, or else the only one that is not a utility; two that fit or none leave the choice to the player."""
    none = {'program': None, 'candidates': [], 'rule': None}
    try:
        entries = root_entries(read_sectors(blob, extension))
    except (DiskError, struct.error, IndexError) as exc:
        return {**none, 'reason': f'disk 1 has no readable DOS root directory ({exc})'}
    if any(e['attr'] & 0x10 and e['name'] == 'AUTO' for e in entries):
        return {**none, 'reason': 'disk 1 has an AUTO folder, which starts its own programs'}
    programs = [e for e in entries if not e['attr'] & 0x1A and e['ext'] in PROGRAM_EXTENSIONS and e['name']
                and not e['name'].startswith(INSTALLER_PREFIX)]
    names = [f"{e['name']}.{e['ext']}" for e in programs]
    def start(index: int) -> str:
        return 'A:' + chr(92) + names[index]
    if len(programs) == 1:
        return {'program': start(0), 'candidates': names, 'rule': 'only-program',
                'reason': 'the only program to open in the root of disk 1'}
    if not programs:
        return {**none, 'reason': 'disk 1 holds no program to open in its root: a disk that starts by itself needs none; if the boot stops at the desktop, the player opens what the disk offers'}
    listed = ', '.join(names)
    words = title_words(title)
    named = [i for i, e in enumerate(programs) if _squash(e['name']) in words]
    if len(named) == 1:
        return {'program': start(named[0]), 'candidates': names, 'rule': 'title-word',
                'reason': f'disk 1 holds {len(programs)} programs ({listed}); the one named like a word of the title'}
    if len(named) > 1:
        return {**none, 'candidates': names, 'reason': f'disk 1 holds {len(programs)} programs ({listed}) and {len(named)} are named like a word '
                f'of the title: if the boot stops at the desktop, the player chooses which to open'}
    games = [i for i, e in enumerate(programs) if not is_utility(e['name'])]
    if len(games) == 1:
        return {'program': start(games[0]), 'candidates': names, 'rule': 'only-non-utility',
                'reason': f'disk 1 holds {len(programs)} programs ({listed}); the only one that is not a utility'}
    return {**none, 'candidates': names, 'reason': f'disk 1 holds {len(programs)} programs ({listed}) and no rule picks one: if the boot stops '
            f'at the desktop, the player chooses which to open'}


def autostart_program(blob: bytes, extension: str, title: str = '') -> tuple[str | None, str]:
    """The program the desktop should start ('A:\\NAME.PRG') and why, or None and why not."""
    decision = autostart_decision(blob, extension, title)
    return decision['program'], decision['reason']
