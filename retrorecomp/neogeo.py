"""Neo Geo multi-region inputs. No source extraction or writes beside ROMs.

The catalogue describes cartridge wiring, not a list of qualified games.
Exact identity includes all original member contents and the selected BIOS.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from zipfile import ZipFile

from . import zip_sets

MAX_SET_BYTES = 512 * 1024 * 1024
# A merged ZIP can contain several complete revisions. Hash them by streaming;
# prepared single cartridges still retain the smaller 512 MiB bound.
MAX_ARCHIVE_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
REGION_NAMES = ('p', 's', 'm', 'v1', 'v2', 'c')
REGION_LIMITS = (16 << 20, 512 << 10, 512 << 10, 128 << 20, 128 << 20, 128 << 20)
BIOS_MEMBERS = {'sp-s2.sp1': (0x20000, 0x9036d879),
                'sfix.sfix': (0x20000, 0xc2ea0cfd),
                'sm1.sm1': (0x20000, 0x94416d67),
                '000-lo.lo': (0x20000, 0x5a86cff2)}


@dataclass(frozen=True)
class NeoGeoSet:
    path: Path
    title: str
    set_name: str
    members: tuple[dict, ...]
    sha256: str
    parent: str = ''
    board: str = ''
    system_id: str = 'ng'
    standard: str = 'mvs'
    ngh: int = 0

    @property
    def size(self):
        return sum(item['bytes'] for item in self.members)

    def metadata(self):
        return {'console': self.system_id, 'title': self.title, 'set': self.set_name,
                'sha256': self.sha256, 'members': list(self.members),
                'parent': self.parent, 'board': self.board, 'standard': self.standard,
                'ngh': self.ngh}


def archive_members(path: Path, *, hash_contents: bool = False, cartridge_paths: bool = False) -> tuple[dict, ...]:
    """Bounds before decompression; CRC validation when original bytes are read."""
    records = []
    with zip_sets.zip_errors('Neo Geo'):
        zip_sets.check_size(path, MAX_SET_BYTES, label='Neo Geo')
        with ZipFile(path) as archive:
            entries = zip_sets.bounded_entries(archive, label='Neo Geo', max_members=1024,
                                               max_expanded=MAX_ARCHIVE_EXPANDED_BYTES)
            seen = set()
            for entry in entries:
                name = zip_sets.flat_name(entry.filename)
                unique = entry.filename.replace('\\', '/').casefold() if cartridge_paths else name
                if not name or unique in seen or entry.flag_bits & 1:
                    raise ValueError('Ambiguous or encrypted Neo Geo archive member.')
                seen.add(unique)
                if entry.file_size > MAX_MEMBER_BYTES:
                    raise ValueError('Neo Geo archive member exceeds the size limit.')
                record = {'name': name, 'bytes': entry.file_size, 'crc32': entry.CRC}
                if cartridge_paths:
                    record['archive_path'] = entry.filename
                if hash_contents:
                    digests = zip_sets.read_member_digests(archive, entry, entry.file_size,
                                                           ('sha256',), label='Neo Geo')
                    record['sha256'] = digests['sha256']
                records.append(record)
    return tuple(sorted(records, key=lambda item: item['name']))


def looks_like_neogeo_zip(path: Path) -> bool:
    members = archive_members(path, cartridge_paths=True)
    kinds = {match[1] for item in members
             if (match := re.search(r'[-.]e?([psmcv])\d(?:[.-]|$)', item['name']))}
    return {'p', 'c', 'm'} <= kinds


def identify_set(path: Path, catalogue: list[dict], *, set_name: str | None = None) -> dict:
    members = archive_members(path, cartridge_paths=True)
    crcs = {item['crc32'] for item in members}
    # Program CRC identifies the revision even when the ZIP or members were renamed.
    candidates = [game for game in catalogue
                  if (programs := [item for item in game['files']
                                   if item['region'] == 0 and not item['optional']])
                  and all(item['crc32'] in crcs for item in programs)]
    if set_name:
        candidates = [game for game in candidates if game['set'] == set_name]
    if not candidates:
        raise ValueError('Neo Geo program revision/layout not recognized. Provide its cartridge manifest; another game profile cannot be used.')
    # A merged set can contain complete layouts for several revisions. Prefer
    # its named revision only after its program AND required component CRCs
    # have matched, instead of favouring whichever clone uses more files.
    named=[game for game in candidates if game['set'].casefold()==path.stem.casefold() and
           all(item['optional'] or item['crc32'] in crcs for item in game['files'])]
    if len(named)==1:
        return named[0]
    complete=[game for game in candidates if all(item['optional'] or item['crc32'] in crcs for item in game['files'])]
    if len(complete)>1:
        raise ValueError('Ambiguous Neo Geo set: select '+', '.join(game['set'] for game in complete))
    # Rank complete member matches. The filename alone never creates a match.
    def rank(game):
        return sum(item['crc32'] in crcs for item in game['files'] if not item['optional'])
    maximum = max(map(rank, candidates))
    candidates = [game for game in candidates if rank(game) == maximum]
    if len(candidates) > 1:
        named = [game for game in candidates if game['set'].casefold() == path.stem.casefold()]
        if len(named) == 1:
            return named[0]
        raise ValueError('Ambiguous Neo Geo set: select ' + ', '.join(game['set'] for game in candidates))
    return candidates[0]


def selected_members(records: tuple[dict, ...], descriptor: dict) -> tuple[dict, ...]:
    """Select a layout by CRC; collisions with different SHA256 remain errors."""
    selected=[]
    for component in descriptor['files']:
        candidates=[r for r in records if r['crc32']==component['crc32']]
        if not candidates:
            if not component['optional'] and not descriptor.get('parent'):
                raise ValueError('Neo Geo cartridge is missing '+component['name']+'.')
            continue
        if len({(r['bytes'],r.get('sha256')) for r in candidates})!=1:
            raise ValueError('Ambiguous Neo Geo component content: '+component['name']+'.')
        chosen=dict(sorted(candidates,key=lambda r:r.get('archive_path',r['name']))[0])
        chosen['name']=component['name'].casefold()
        selected.append(chosen)
    return tuple(sorted(selected,key=lambda r:r['name']))


def canonical_archive(source: Path, destination: Path, descriptor: dict) -> None:
    """Only write a local staged archive; never extract or change the input."""
    from zipfile import ZipInfo, ZIP_DEFLATED
    if source.resolve()==destination.resolve():
        raise ValueError('Neo Geo staging must not replace its input archive.')
    records=archive_members(source,hash_contents=True,cartridge_paths=True)
    chosen=selected_members(records,descriptor)
    with ZipFile(source) as original, ZipFile(destination,'w',compression=ZIP_DEFLATED) as staged:
        for item in chosen:
            data=original.read(item['archive_path'])
            if hashlib.sha256(data).hexdigest()!=item['sha256']:
                raise ValueError('Neo Geo source changed during cartridge staging.')
            entry=ZipInfo(item['name'],date_time=(1990,1,1,0,0,0));entry.compress_type=ZIP_DEFLATED
            staged.writestr(entry,data)


def mirror_short_fixed_rom(container: Path) -> bool:
    """Repeat a fixed-graphics ROM smaller than 128 KiB (a 64 KiB chip) up to 128 KiB in the staged container.

    The video chip numbers fix tiles with 12 bits and the chip's unused address lines repeat its contents, so tile n of a
    64 KiB ROM is tile n - 2048 above 2048 (MAME wraps the tile code the same way). The reference engine indexes the
    region without a mask, and the layout check below wants at least 128 KiB: a 64 KiB region would be read past its end.
    Only the container staged for this conversion is rewritten (never a caller's file); returns whether it changed."""
    size = container.stat().st_size
    if not 4096 <= size <= MAX_SET_BYTES:
        return False
    with container.open('rb') as source:
        header = bytearray(source.read(4096))
        if header[:4] != b'NEO':
            return False
        lengths = list(struct.unpack_from('<6I', header, 4))
        fixed = lengths[1]
        if fixed >= 0x20000 or fixed < 0x4000 or fixed & (fixed - 1) or 4096 + sum(lengths) != size:
            return False
        target = container.with_name(container.name + '.mirror')
        copies = 0x20000 // fixed
        with target.open('wb') as out:
            lengths[1] = 0x20000
            struct.pack_into('<6I', header, 4, *lengths)
            out.write(header)
            for index, length in enumerate((lengths[0], fixed, *lengths[2:])):
                left = length
                data = b''
                while left:
                    chunk = source.read(min(left, 1 << 20))
                    if not chunk:
                        raise ValueError('Truncated NEO region.')
                    if index == 1:
                        data += chunk
                    else:
                        out.write(chunk)
                    left -= len(chunk)
                if index == 1:
                    out.write(data * copies)
    target.replace(container)
    return True


def parse_neo(path: Path) -> NeoGeoSet:
    size = path.stat().st_size
    if not 4096 <= size <= MAX_SET_BYTES:
        raise ValueError('Invalid NEO container size.')
    with path.open('rb') as source:
        header = source.read(4096)
        if header[:4] != b'NEO\x01':
            raise ValueError('Invalid NEO signature/version.')
        lengths = struct.unpack_from('<6I', header, 4)
        if 4096 + sum(lengths) != size:
            raise ValueError('NEO region sizes do not match the file.')
        for name, length, limit in zip(REGION_NAMES, lengths, REGION_LIMITS):
            if length > limit or (name in ('p', 's', 'm', 'c') and length == 0):
                raise ValueError(f'Invalid NEO {name.upper()} region size.')
        if lengths[0] < 0x200 or lengths[1] < 0x20000 or lengths[1] % 0x20000:
            raise ValueError('NEO program/fixed graphics are smaller than the cartridge layout.')
        if lengths[2] < 0x10000 or lengths[2] & (lengths[2] - 1):
            raise ValueError('Invalid NEO sound-program ROM layout.')
        if lengths[0] & 1 or lengths[-1] % 128:
            raise ValueError('Misaligned NEO program or sprite region.')
        regions = []
        offset = 4096
        for name, length in zip(REGION_NAMES, lengths):
            digest = hashlib.sha256()
            left = length
            while left:
                chunk = source.read(min(left, 1024 * 1024))
                if not chunk: raise ValueError('Truncated NEO region.')
                digest.update(chunk); left -= len(chunk)
            regions.append({'region': name, 'bytes': length, 'offset': offset,
                            'sha256': digest.hexdigest()})
            offset += length
    title = header[44:77].split(b'\0', 1)[0].decode('ascii', errors='replace').strip()
    ngh = struct.unpack_from('<I', header, 40)[0]
    identity = hashlib.sha256(json.dumps({'regions': regions, 'ngh': ngh}, sort_keys=True).encode()).hexdigest()
    return NeoGeoSet(path, title or path.stem, path.stem, tuple(regions), identity, ngh=ngh)


def read_set(path: Path, catalogue: list[dict] | None = None, *, set_name=None) -> NeoGeoSet:
    if path.suffix.casefold() == '.neo': return parse_neo(path)
    if catalogue is None:
        from .neogeo_catalogue import catalogue as bundled_catalogue
        catalogue = bundled_catalogue()
    descriptor = identify_set(path, catalogue, set_name=set_name)
    records=archive_members(path,hash_contents=True,cartridge_paths=True)
    # The layout is checked even for a conventional archive. Only merged
    # archives need to remove competing revisions from their identity here.
    selected=selected_members(records,descriptor)
    members=(selected if len({r['name'] for r in records})!=len(records) else records)
    members=tuple({k:v for k,v in r.items() if k!='archive_path'} for r in members)
    # ZIP layout, timestamps and member aliases do not change cartridge bytes.
    contents = sorted((item['bytes'], item['sha256']) for item in members)
    identity = hashlib.sha256(json.dumps(contents).encode()).hexdigest()
    return NeoGeoSet(path, descriptor['title'], descriptor['set'], members, identity,
                     descriptor.get('parent', ''), descriptor.get('board', ''))


def parent_archives(game: NeoGeoSet, catalogue: list[dict]) -> list[tuple[Path, tuple[dict, ...]]]:
    """A complete clone needs no parent, regardless of its archive filename."""
    if not game.parent:
        return []
    descriptor = next(row for row in catalogue if row['set'] == game.set_name)
    present = {member['crc32'] for member in game.members}
    missing = [part for part in descriptor['files'] if not part['optional'] and part['crc32'] not in present]
    if not missing:
        return []
    parent = game.path.parent / (game.parent + '.zip')
    if parent.resolve() == game.path.resolve() or not parent.is_file():
        raise ValueError('Neo Geo split cartridge requires a separate ' + game.parent +
                         '.zip parent archive for ' + ', '.join(part['name'] for part in missing) + '.')
    records = archive_members(parent, hash_contents=True, cartridge_paths=True)
    available = {record['crc32'] for record in records}
    if any(part['crc32'] not in available for part in missing):
        raise ValueError('Neo Geo parent archive does not contain the required cartridge components.')
    return [(parent, records)]


def validate_bios(path: Path | None) -> dict:
    # No BIOS chosen (an empty Options field): say so, instead of failing deeper on a missing path.
    if path is None:
        raise ValueError('Neo Geo needs the MVS BIOS archive (neogeo.zip): choose it in Options, Neo Geo page, '
                         'then convert again.')
    members = archive_members(path, hash_contents=True)
    by_name = {item['name']: item for item in members}
    selected = []
    for name, (size, crc) in BIOS_MEMBERS.items():
        item = by_name.get(name)
        if not item:
            raise ValueError(f'MVS Europe BIOS requires {name} in the selected archive.')
        if item['bytes'] != size or item['crc32'] != crc:
            raise ValueError(f'Incorrect BIOS revision/content: {name}.')
        selected.append(item)
    identity = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    result = {'system': 'mvs', 'region': 'eu', 'members': selected, 'sha256': identity}
    aes = by_name.get('neo-epo.bin')
    if aes:
        if aes['bytes'] != 0x20000 or aes['crc32'] != 0xd27a71f1:
            raise ValueError('Incorrect AES export BIOS revision/content: neo-epo.bin.')
        result['aes'] = aes
    return result


def combined_identity(game: NeoGeoSet, bios: dict, *, engine_revision: str, loader_revision: str) -> str:
    layout = {'ngh': game.ngh} if game.path.suffix.casefold() == '.neo' else {
        'set': game.set_name, 'board': game.board}
    descriptor = {'game': game.sha256, 'layout': layout, 'bios': bios['sha256'], 'system': bios['system'],
                  'region': bios['region'], 'engine': engine_revision, 'loader': loader_revision}
    return hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
