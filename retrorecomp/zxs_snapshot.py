"""ZX Spectrum snapshots as the converter reads them (docs/ZX_SPECTRUM.md): `.z80` (versions 1, 2 and 3) and `.sna`
(48K and 128K), from a file or from a ZIP holding exactly one. MIT, our own code, written from the public format
descriptions (the World of Spectrum `.z80` reference and the `.sna` layout); libspectrum and Fuse (GPL) were not used.

A snapshot is the machine's RAM and registers at one moment, saved after the game had loaded: no tape loader runs here.
It holds no ROM (the converter adds the Spectrum ROM, retrorecomp/zxs_roms.py). The reader refuses, with a sentence, what
it cannot model yet: the +2A and +3, the Pentagon, Scorpion, SamRam, Timex and Didaktik machines, a snapshot taken with
the Interface 1 or the TR-DOS ROM paged in, one that carries a ROM page of its own, and any file whose blocks do not
decode to whole 16 KiB pages.

Memory is given as the 128K's eight RAM banks of 16 KiB (`banks`): a 48K snapshot fills banks 5, 2 and 0 (the RAM at
4000h, 8000h and C000h, as a 128K maps them at reset), a 16K one bank 5 only. Nothing here is a ROM byte or a game byte
kept in the repository; the tests build their snapshots themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path

EXTENSIONS = ('.z80', '.sna')
PAGE = 0x4000
# The largest snapshot read: a 128K `.z80` stored uncompressed is 8 pages of 16 KiB plus 3 bytes each and an 87-byte
# header; a 128K `.sna` with a duplicated bank is 147,487 bytes. 192 KiB covers both with room for odd headers.
MAX_BYTES = 0x30000
SNA48_BYTES = 27 + 3 * PAGE                 # 49,179
SNA128_BYTES = (SNA48_BYTES + 4 + 5 * PAGE, SNA48_BYTES + 4 + 6 * PAGE)   # 131,103 and 147,487

# The machines the converter models: the snapshot's own hardware word is kept beside it (`hardware`).
MODELS = ('16k', '48k', '128k')
# `.z80` hardware mode (byte 34) by header version: the model, or None when it is a machine the converter refuses.
# Version 2: 0 48K, 1 48K + Interface 1, 2 SamRam, 3 128K, 4 128K + Interface 1. Version 3: 0 48K, 1 48K + Interface 1,
# 2 SamRam, 3 48K + M.G.T., 4 128K, 5 128K + Interface 1, 6 128K + M.G.T.; and the extensions other tools write: 7 and 8
# +3, 9 Pentagon 128, 10 Scorpion 256, 11 Didaktik Kompakt, 12 +2, 13 +2A, 14 TC2048, 15 TC2068, 128 TS2068.
_Z80_V2_MODES = {0: ('48k', '48K'), 1: ('48k', '48K + Interface 1'), 2: (None, 'SamRam'), 3: ('128k', '128K'),
                 4: ('128k', '128K + Interface 1'), 7: (None, '+3'), 8: (None, '+3'), 9: (None, 'Pentagon 128'),
                 10: (None, 'Scorpion 256'), 11: (None, 'Didaktik Kompakt'), 12: ('128k', '+2'), 13: (None, '+2A'),
                 14: (None, 'TC2048'), 15: (None, 'TC2068'), 128: (None, 'TS2068')}
_Z80_V3_MODES = {**_Z80_V2_MODES, 3: ('48k', '48K + M.G.T.'), 4: ('128k', '128K'), 5: ('128k', '128K + Interface 1'),
                 6: ('128k', '128K + M.G.T.')}
# The joystick the snapshot was saved for (byte 29, bits 6-7).
JOYSTICKS = ('cursor', 'kempston', 'sinclair-left', 'sinclair-right')


@dataclass(frozen=True)
class Snapshot:
    """One snapshot: the file's bytes and their SHA-256 (the game's identity), the model and what the machine held."""
    path: Path
    data: bytes
    sha256: str
    format: str                  # 'z80' or 'sna'
    version: int                 # 1, 2 or 3 for a .z80; 0 for a .sna
    model: str                   # one of MODELS
    hardware: str                # the snapshot's own word for the machine ('48K', '+2', '128K + Interface 1'...)
    registers: dict              # af bc de hl af_ bc_ de_ hl_ ix iy sp pc i r iff1 iff2 im
    border: int
    port_7ffd: int | None        # the last value written to 7FFDh (128K), None on a 48K
    ay_select: int | None        # the AY register selected and the sixteen registers (128K .z80 v2/v3), None otherwise
    ay_registers: tuple | None
    joystick: str | None         # one of JOYSTICKS for a .z80, None for a .sna (it does not say)
    tstates: int | None          # T-states into the frame (.z80 v3), None when the file does not say
    banks: dict = field(repr=False)   # RAM bank number -> 16 KiB
    member: str = ''             # the snapshot's name inside a ZIP, '' for a file

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def game_key(self) -> str:
        return self.sha256

    def metadata(self) -> dict:
        return {'path': str(self.path), 'member': self.member, 'bytes': self.size, 'sha256': self.sha256,
                'format': self.format, 'version': self.version, 'model': self.model, 'hardware': self.hardware,
                'joystick': self.joystick, 'banks': sorted(self.banks)}


def _word(data: bytes, at: int) -> int:
    return data[at] | data[at + 1] << 8


def _rle(stream: bytes, size: int | None, end_marker: bool, name: str) -> bytes:
    """The `.z80` compression: ED ED nn bb is nn times bb; version 1 ends at 00 ED ED 00. `size` is what it must give."""
    out = bytearray()
    at, length = 0, len(stream)
    while at < length:
        if end_marker and stream[at:at + 4] == b'\x00\xED\xED\x00':
            at = length
            break
        if stream[at] == 0xED and at + 1 < length and stream[at + 1] == 0xED:
            if at + 3 >= length:
                raise ValueError(f'{name}: a compressed block ends inside a repeat.')
            out += bytes((stream[at + 3],)) * stream[at + 2]
            at += 4
        else:
            out.append(stream[at])
            at += 1
        if size is not None and len(out) > size:
            raise ValueError(f'{name}: a compressed block decodes to more than {size} bytes.')
    if size is not None and len(out) != size:
        raise ValueError(f'{name}: a compressed block decodes to {len(out)} bytes, not {size}.')
    return bytes(out)


def _z80(data: bytes, name: str) -> dict:
    if len(data) < 30:
        raise ValueError(f'{name}: too short for a .z80 header.')
    flags = data[12] if data[12] != 0xFF else 1          # 255 means 1 (the format's own rule)
    info = data[29]
    regs = {'af': data[0] << 8 | data[1], 'bc': _word(data, 2), 'hl': _word(data, 4), 'pc': _word(data, 6),
            'sp': _word(data, 8), 'i': data[10], 'r': (data[11] & 0x7F) | (flags & 1) << 7, 'de': _word(data, 13),
            'bc_': _word(data, 15), 'de_': _word(data, 17), 'hl_': _word(data, 19),
            'af_': data[21] << 8 | data[22], 'iy': _word(data, 23), 'ix': _word(data, 25),
            'iff1': int(bool(data[27])), 'iff2': int(bool(data[28])), 'im': info & 3}
    found = {'registers': regs, 'border': flags >> 1 & 7, 'joystick': JOYSTICKS[info >> 6], 'port_7ffd': None,
             'ay_select': None, 'ay_registers': None, 'tstates': None}
    if regs['im'] == 3:
        raise ValueError(f'{name}: interrupt mode 3 is not a Z80 mode; the header is damaged.')
    if regs['pc']:                                      # version 1: a 48K, its RAM right after the header
        # Bit 4 of byte 12 ("SamRom switched in") means something only on a SamRam, which a version 1 file cannot be: 20 of
        # the 137 version 1 files of the maintainer's library set it on plain 48K snapshots (Manic Miner among them).
        body = data[30:]
        ram = _rle(body, 3 * PAGE, True, name) if flags & 0x20 else body
        if len(ram) != 3 * PAGE:
            raise ValueError(f'{name}: a version 1 .z80 holds 48 KiB of RAM; this one holds {len(ram)} bytes.')
        found.update(version=1, model='48k', hardware='48K',
                     banks={5: ram[:PAGE], 2: ram[PAGE:2 * PAGE], 0: ram[2 * PAGE:]})
        return found
    if len(data) < 32:
        raise ValueError(f'{name}: too short for a .z80 extended header.')
    extra = _word(data, 30)
    version = {23: 2, 54: 3, 55: 3}.get(extra)
    if version is None or len(data) < 32 + extra:
        raise ValueError(f'{name}: unknown .z80 extended header ({extra} bytes).')
    header = data[:32 + extra]
    regs['pc'] = _word(header, 32)
    mode = header[34]
    model, hardware = (_Z80_V2_MODES if version == 2 else _Z80_V3_MODES).get(mode, (None, f'hardware {mode}'))
    modified = bool(header[37] & 0x80)
    if model == '48k' and modified:
        model, hardware = '16k', '16K'
    elif model == '128k' and modified:
        hardware = '+2'                                   # the modified-hardware bit turns a 128K into a +2
    if model is None:
        raise ValueError(f'{name}: a snapshot of the {hardware}, a machine the converter does not convert yet '
                         '(16K, 48K, 128K and +2 only).')
    if 'Interface 1' in hardware and header[36] == 0xFF:
        raise ValueError(f'{name}: saved with the Interface 1 ROM paged in, which the converter does not model.')
    if model == '128k':
        found['port_7ffd'] = header[35]
    if header[37] & 0x04 or model == '128k':
        found['ay_select'] = header[38] & 0x0F
        found['ay_registers'] = tuple(header[39:55])
    if version == 3:
        low, high = _word(header, 55), header[57]
        # The high counter is 3 just after the interrupt and counts quarters of a frame; the low one counts down from
        # 17471 (17726 on a 128K) inside each quarter: 69,888 (70,908) T-states a frame.
        quarter = 17727 if model == '128k' else 17472
        if low < quarter and high < 4:
            found['tstates'] = ((high + 1) % 4 + 1) * quarter - (low + 1)
    banks: dict[int, bytes] = {}
    at = len(header)
    while at < len(data):
        if at + 3 > len(data):
            raise ValueError(f'{name}: a memory block header is cut.')
        length, page = _word(data, at), data[at + 2]
        at += 3
        stored = PAGE if length == 0xFFFF else length
        if at + stored > len(data):
            raise ValueError(f'{name}: a memory block is cut.')
        block = data[at:at + stored]
        at += stored
        memory = block if length == 0xFFFF else _rle(block, PAGE, False, name)
        if page < 3:
            raise ValueError(f'{name}: the snapshot carries a ROM page of its own (page {page}); '
                             'the converter runs the original Spectrum ROM only.')
        if model == '128k':
            bank = page - 3 if page <= 10 else None
        else:
            bank = {8: 5, 4: 2, 5: 0}.get(page)
        if bank is None:
            raise ValueError(f'{name}: memory page {page} does not exist on the {hardware}.')
        if bank in banks:
            raise ValueError(f'{name}: memory page {page} is stored twice.')
        banks[bank] = memory
    needed = {'16k': {5}, '48k': {5, 2, 0}, '128k': set(range(8))}[model]
    if not needed <= set(banks):
        raise ValueError(f'{name}: memory pages are missing for the {hardware} '
                         f'(RAM banks {", ".join(str(b) for b in sorted(needed - set(banks)))}).')
    if model == '16k':
        banks = {5: banks[5]}                             # what a 16K never had is not memory
    found.update(version=version, model=model, hardware=hardware, banks=banks)
    return found


def _sna(data: bytes, name: str) -> dict:
    if len(data) != SNA48_BYTES and len(data) not in SNA128_BYTES:
        raise ValueError(f'{name}: {len(data)} bytes is not the size of a 48K or a 128K .sna.')
    regs = {'i': data[0], 'hl_': _word(data, 1), 'de_': _word(data, 3), 'bc_': _word(data, 5), 'af_': _word(data, 7),
            'hl': _word(data, 9), 'de': _word(data, 11), 'bc': _word(data, 13), 'iy': _word(data, 15),
            'ix': _word(data, 17), 'iff1': int(bool(data[19] & 4)), 'iff2': int(bool(data[19] & 4)), 'r': data[20],
            'af': _word(data, 21), 'sp': _word(data, 23), 'im': data[25]}
    if regs['im'] > 2:
        raise ValueError(f'{name}: interrupt mode {regs["im"]} is not a Z80 mode; the header is damaged.')
    ram = data[27:SNA48_BYTES]
    found = {'registers': regs, 'border': data[26] & 7, 'joystick': None, 'ay_select': None, 'ay_registers': None,
             'tstates': None, 'version': 0}
    if len(data) == SNA48_BYTES:
        banks = {5: ram[:PAGE], 2: ram[PAGE:2 * PAGE], 0: ram[2 * PAGE:]}
        sp = regs['sp']
        if sp < 0x4000 or sp > 0xFFFE:
            raise ValueError(f'{name}: the stack pointer of a 48K .sna is outside RAM; the PC cannot be read.')

        def byte(address: int) -> int:
            return banks[{1: 5, 2: 2, 3: 0}[address >> 14]][address & 0x3FFF]
        regs['pc'] = byte(sp) | byte(sp + 1) << 8         # a 48K .sna keeps its PC on the stack (RETN)
        regs['sp'] = (sp + 2) & 0xFFFF
        found.update(model='48k', hardware='48K', port_7ffd=None, banks=banks)
        return found
    tail = data[SNA48_BYTES:]
    regs['pc'] = _word(tail, 0)
    port = tail[2]
    if tail[3]:
        raise ValueError(f'{name}: saved with the TR-DOS ROM paged in, which the converter does not model.')
    paged = port & 7
    banks = {5: ram[:PAGE], 2: ram[PAGE:2 * PAGE], paged: ram[2 * PAGE:]}
    rest = [bank for bank in range(8) if bank not in (5, 2, paged)]
    if len(tail) - 4 != len(rest) * PAGE:
        raise ValueError(f'{name}: a 128K .sna with bank {paged} paged holds {len(rest)} more banks; the size disagrees.')
    for index, bank in enumerate(rest):
        banks[bank] = tail[4 + index * PAGE:4 + (index + 1) * PAGE]
    found.update(model='128k', hardware='128K', port_7ffd=port, banks=banks)
    return found


def _from_zip(path: Path) -> tuple[bytes, str, str]:
    import zipfile
    import zlib
    try:
        with zipfile.ZipFile(path) as bundle:
            names = [n for n in bundle.namelist() if not n.endswith('/') and Path(n).suffix.casefold() in EXTENSIONS]
            if len(names) != 1:
                raise ValueError(f'{path.name}: the ZIP must hold exactly one ZX Spectrum snapshot (.z80 or .sna).')
            if bundle.getinfo(names[0]).file_size > MAX_BYTES:
                raise ValueError(f'{path.name}: larger than any ZX Spectrum snapshot the converter reads.')
            return bundle.read(names[0]), names[0], Path(names[0]).suffix.casefold()
    except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
        raise ValueError(f'{path.name}: not a readable ZIP ({error}).') from None


def zip_holds_snapshot(path: Path) -> bool:
    """True when a ZIP holds exactly one .z80 or .sna (its names only: a ZIP of another machine is never read)."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as bundle:
            return sum(Path(n).suffix.casefold() in EXTENSIONS for n in bundle.namelist() if not n.endswith('/')) == 1
    except (OSError, zipfile.BadZipFile):
        return False


def parse(data: bytes, suffix: str, name: str = 'snapshot') -> dict:
    """The fields of a snapshot from its bytes (`suffix`: '.z80' or '.sna'), or ValueError with a sentence."""
    if suffix == '.z80':
        return _z80(data, name)
    if suffix == '.sna':
        return _sna(data, name)
    raise ValueError(f'{name}: not a ZX Spectrum snapshot (.z80 or .sna).')


def read_snapshot(path) -> Snapshot:
    """The snapshot at `path` (.z80, .sna, or a ZIP holding one), refused with a sentence when it is none."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == '.zip':
        data, member, suffix = _from_zip(path)
    else:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f'{path.name}: larger than any ZX Spectrum snapshot the converter reads.')
        data, member = path.read_bytes(), ''
    found = parse(data, suffix, path.name)
    return Snapshot(path=path, data=data, sha256=hashlib.sha256(data).hexdigest(), format=suffix[1:], member=member,
                    **found)
