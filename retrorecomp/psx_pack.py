"""The disc pack of a PlayStation game (Retro-Recomp's own code, MIT): the player's disc as the core reads it.

The machine (native/psx_machine/psx_session.c) reads its discs through a virtual file system that serves the files a pack names.
A pack is a manifest at the end of a file, after the data it describes:

    [prefix: the game program, or nothing][data...][manifest][trailer: b'RRPSXPK1', u64 manifest offset, u64 manifest size]

Two kinds of pack carry the same manifest:

* **in place** (the conversion's reference runs): the data of the player's files stays where it is; the manifest names those
  files by path (`source <n> <path>`) and only the sheets we write are stored in the pack;
* **embedded** (the exported game): every byte the core reads is appended to the game program, so the game holds the whole disc
  and reads it in place, as the adventure games are packed. An EBOOT keeps its compressed blocks: they are inflated as they are read.

The core loads one sheet per disc: the player's CloneCD control file, or a CUE sheet we write from the disc's own geometry (for a
CUE/BIN set, a bare image, an ISO and an EBOOT). Names inside the pack are ours (`disc1.cue`, `disc1-1.bin`...): a player's file
name never reaches the core.
"""
from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from . import psx_disc

MAGIC = b'RRPSXPK1'
FORMAT_LINE = 'RRPSX-PACK 1'
CHUNK = 8 * 1024 * 1024


@dataclass
class _Entry:
    name: str
    kind: str                  # 'raw', 'pbp' or 'text'
    path: Path | None = None   # raw/pbp: the player's file
    offset: int = 0
    size: int = 0
    text: bytes = b''
    image: int = 0             # pbp
    data: int = 0
    blocks: int = 0


def _msf(frames: int) -> str:
    return f'{frames // 4500:02d}:{frames // 75 % 60:02d}:{frames % 75:02d}'


def _cue_for(disc: psx_disc.Disc, names: dict) -> bytes:
    """A CUE sheet of the disc's tracks over the pack's files (`names`: source object -> pack name)."""
    lines = []
    current = None
    for track in disc.tracks:
        source = track.source
        if source is not current:
            kind = 'MOTOROLA' if getattr(source, 'swap', False) else 'BINARY'
            lines.append(f'FILE "{names[id(source)]}" {kind}')
            current = source
        lines.append(f'  TRACK {track.number:02d} {track.mode}')
        stride = source.stride
        position = track.offset // stride
        unstored = track.pregap - track.stored_pregap
        if unstored and track.number > 1:
            lines.append(f'    PREGAP {_msf(unstored)}')
        if track.stored_pregap:
            lines.append(f'    INDEX 00 {_msf(position - track.stored_pregap)}')
        lines.append(f'    INDEX 01 {_msf(position)}')
    return ('\r\n'.join(lines) + '\r\n').encode('ascii')


def entries(path: Path) -> tuple[list[_Entry], list[str]]:
    """The files of every disc of `path` and the sheet the core loads for each disc."""
    path = Path(path)
    out: list[_Entry] = []
    sheets: list[str] = []
    for index in range(psx_disc.disc_count(path)):
        disc = psx_disc.open_disc(path, index)
        try:
            stem = f'disc{index + 1}'
            if disc.container == 'ccd':
                image, sub = disc.sources[0], disc.sources[1] if len(disc.sources) > 1 else None
                ccd = disc.path
                out.append(_Entry(f'{stem}.ccd', 'raw', ccd, 0, ccd.stat().st_size))
                out.append(_Entry(f'{stem}.img', 'raw', image.path, 0, image.size))
                if sub is not None:
                    out.append(_Entry(f'{stem}.sub', 'raw', sub.path, 0, sub.size))
                sheets.append(f'{stem}.ccd')
                continue
            names = {}
            for number, source in enumerate(disc.sources, start=1):
                name = f'{stem}-{number}.bin'
                names[id(source)] = name
                if isinstance(source, psx_disc._PbpSource):
                    # The image ends at the disc's lead-out (its last block is padded to 16 sectors).
                    image_offset = psx_disc.pbp_info(path).images[index]
                    size = min(disc.leadout, len(source.blocks) * psx_disc.PBP_BLOCK_SECTORS) * psx_disc.SECTOR
                    out.append(_Entry(name, 'pbp', source.path, image=image_offset, data=_pbp_data_base(path, image_offset),
                                      blocks=len(source.blocks), size=size))
                else:
                    out.append(_Entry(name, 'raw', source.path, 0, source.size))
            out.append(_Entry(f'{stem}.cue', 'text', text=_cue_for(disc, names)))
            sheets.append(f'{stem}.cue')
        finally:
            disc.close()
    return out, sheets


def _pbp_data_base(path: Path, image: int) -> int:
    """The file offset an EBOOT disc's block offsets count from (psx_disc.read_pbp's rule)."""
    with open(path, 'rb') as f:
        f.seek(image + 0xBFC)
        data_offset = struct.unpack('<I', f.read(4))[0]
    return image + (data_offset if data_offset else 0x100000)


def _manifest(lines: list[str]) -> bytes:
    return ('\n'.join([FORMAT_LINE, *lines]) + '\n').encode('utf-8')


def _trailer(offset: int, size: int) -> bytes:
    return MAGIC + struct.pack('<QQ', offset, size)


def write_in_place(path: Path, pack: Path) -> Path:
    """A pack file for the conversion's reference runs: the player's files are named where they are (never copied)."""
    files, sheets = entries(path)
    sources: dict[Path, int] = {}
    lines = []
    body = bytearray()
    for e in files:
        if e.kind == 'text':
            lines.append(f'file {e.name} raw 0 {len(body)} {len(e.text)}')
            body += e.text
            continue
        if e.path not in sources:
            sources[e.path] = len(sources) + 1
            lines.insert(0, f'source {sources[e.path]} {Path(e.path).resolve()}')
        n = sources[e.path]
        if e.kind == 'raw':
            lines.append(f'file {e.name} raw {n} {e.offset} {e.size}')
        else:
            lines.append(f'file {e.name} pbp {n} {e.image} {e.data} {e.blocks} {e.size}')
    lines += [f'disc {s}' for s in sheets]
    manifest = _manifest(lines)
    pack = Path(pack)
    pack.parent.mkdir(parents=True, exist_ok=True)
    with open(pack, 'wb') as f:
        f.write(body)
        f.write(manifest)
        f.write(_trailer(len(body), len(manifest)))
    return pack


def write_embedded(path: Path, program: Path, output: Path) -> Path:
    """The exported game: the program followed by every byte of the disc the core reads, then the manifest."""
    files, sheets = entries(path)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    copied: dict[Path, int] = {}       # an EBOOT whose discs share one file is appended once
    with open(output, 'wb') as out:
        with open(program, 'rb') as f:
            shutil.copyfileobj(f, out, CHUNK)
        for e in files:
            if e.kind == 'text':
                lines.append(f'file {e.name} raw 0 {out.tell()} {len(e.text)}')
                out.write(e.text)
            elif e.kind == 'raw':
                start = out.tell()
                with open(e.path, 'rb') as f:
                    f.seek(e.offset)
                    left = e.size
                    while left:
                        chunk = f.read(min(CHUNK, left))
                        if not chunk:
                            raise psx_disc.DiscError(f'{Path(e.path).name} is shorter than its pack entry')
                        out.write(chunk)
                        left -= len(chunk)
                lines.append(f'file {e.name} raw 0 {start} {e.size}')
            else:
                if e.path not in copied:
                    copied[e.path] = out.tell()
                    with open(e.path, 'rb') as f:
                        shutil.copyfileobj(f, out, CHUNK)
                base = copied[e.path]
                lines.append(f'file {e.name} pbp 0 {base + e.image} {base + e.data} {e.blocks} {e.size}')
        lines += [f'disc {s}' for s in sheets]
        manifest = _manifest(lines)
        offset = out.tell()
        out.write(manifest)
        out.write(_trailer(offset, len(manifest)))
    return output
