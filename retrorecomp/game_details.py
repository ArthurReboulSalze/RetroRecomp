"""Private game cards and artwork, independent of compiler observations.

Reading a card is offline. Network lookup is explicit and console constrained.
"""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import struct
from threading import RLock
import urllib.parse

from PIL import Image

from .compiled_games import read_json, SHA
from .library import atomic_json
from .paths import data_directory, boxart_cache_directory
from .systems import get_profile

_lock = RLock()


def _report_stamp(path):
    try:
        if path and Path(path).is_file():
            value=Path(path).stat()
            return [value.st_size,value.st_mtime_ns]
    except (OSError,TypeError,ValueError):pass
    return None


def _text(value, maximum=500):
    return ''.join(c for c in str(value or '') if c >= ' ' or c in '\n\t')[:maximum].strip()


def synopsis(value):
    """A short frontend synopsis, never a full article or development history."""
    import html
    text=html.unescape(re.sub('<[^>]*>','',str(value or '')))
    text=re.sub(r'\s+',' ',text).strip()
    if len(text)>850:text=text[:847].rsplit(' ',1)[0]+'…'
    return _text(text,850)


def public_url(value):
    try:
        url = urllib.parse.urlsplit(value)
        if url.scheme == 'https' and url.hostname and not url.username and not url.password:
            if not url.query:return value
            params=urllib.parse.parse_qsl(url.query,keep_blank_values=True)
            if params and all(k in ('id','gameid','plateforme') and v.isdecimal() for k,v in params):return value
    except (ValueError, TypeError):pass
    return ''


class Cards:
    def __init__(self, directory=None):
        self.directory = (directory or data_directory())/'game-cards'

    def folder(self, game):
        get_profile(game.system)
        if not SHA.fullmatch(game.identity):raise ValueError('Invalid game identity')
        return self.directory/game.system/game.identity

    def load(self, game):
        try:
            data = read_json(self.folder(game)/'card.json', 128*1024)
            if data.get('identity') == game.identity and data.get('system') == game.system:
                return data
        except (OSError, ValueError, TypeError):pass
        return dict(schema=1, system=game.system, identity=game.identity, languages={})

    def metadata(self, game, language):
        data = self.load(game).get('languages', {})
        return data.get(language, {}) if isinstance(data, dict) else {}

    def save_metadata(self, game, language, record):
        if language not in ('en','fr','de','it','es','ja','zh','ru'):raise ValueError('Invalid language')
        fields = ('title','release','release_scope','developer','publisher','genre','players',
                  'description','provider','source','license','language')
        clean = {key:_text(record.get(key), 6000 if key=='description' else 600) for key in fields}
        clean['description'] = synopsis(clean['description'])
        clean['source'] = public_url(clean['source'])
        clean['fetched'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        with _lock:
            data = self.load(game)
            data.setdefault('languages', {})[language] = clean
            self._save(game, data)
        return clean

    def _save(self, game, data):
        folder = self.folder(game)
        folder.mkdir(parents=True, exist_ok=True)
        atomic_json(folder/'card.json', data)

    def set_cover(self, game, payload, *, override=False, source='', report_stamp=None):
        from .artwork import _image, _atomic
        image = _image(payload)
        bound=1600 if override else 512
        image.thumbnail((bound,bound), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        with _lock:
            folder = self.folder(game)
            folder.mkdir(parents=True, exist_ok=True)
            _atomic(folder/'cover.png', buffer.getvalue())
            data = self.load(game)
            data['cover'] = dict(file='cover.png', override=override, source=public_url(source))
            if not override and report_stamp is not None:
                data['cover']['report_stamp']=report_stamp
            self._save(game, data)
        return folder/'cover.png'

    def override(self, game):
        cover = self.load(game).get('cover', {})
        path = self.folder(game)/'cover.png'
        return path if isinstance(cover, dict) and cover.get('override') is True and path.is_file() else None

    def cover(self, game):
        """Fast cache/report lookup first; only then recover an export's icon."""
        from .artwork import _saved_cover, _read_image, resolve_cover, ArtworkError
        own = self.folder(game)/'cover.png'
        cached=None
        stamp=_report_stamp(game.report)
        if own.is_file():
            try:
                cached=_read_image(own)
                record=self.load(game).get('cover',{})
                if (stamp is None or isinstance(record,dict) and (
                        record.get('override') is True or record.get('report_stamp')==stamp)):
                    return cached
            except (OSError, ValueError):pass
        report = {}
        try:report = read_json(game.report)
        except (OSError, ValueError):pass
        art = report.get('artwork', {})
        if not isinstance(art,dict):art={}
        cache = boxart_cache_directory(game.system)
        # Some cartridge readers normalize headers; saved-art keys hash the
        # original file. Prefer the exact conversion's image path when present.
        choices = [Path(art['image'])] if isinstance(art, dict) and art.get('image') else []
        saved = _saved_cover(cache, game.identity, game.system, False, True)
        if saved:choices.insert(0,saved['path'])
        for path in choices:
            try:
                payload = _read_image(path)
                self.set_cover(game,payload,source=art.get('source_page',''),report_stamp=stamp)
                return payload
            except (OSError, ValueError):pass
        try:
            cover = resolve_cover(Path(game.title+'.rom'),game.title,cache,online=False,
                                  system_id=game.system,settings={'box_3d':False,'accounts':{}},emit=lambda _:None)
            if cover.get('style') not in ('title','snapshot','box3d'):
                self.set_cover(game,cover['data'],source=cover.get('source_page',''),report_stamp=stamp)
                return cover['data']
        except (OSError, ValueError):pass
        if game.report:
            choices = list((Path(game.report).parent/'artwork').glob('*-icon.png'))
        else:choices = []
        choices += [Path(game.executable).parent/'datas/launchers'/f'{game.identity}.png']
        for path in choices:
            try:
                payload = _read_image(path)
                self.set_cover(game,payload,report_stamp=stamp)
                return payload
            except (OSError, ValueError):pass
        try:
            payload = pe_icon(Path(game.executable)) or elf_icon(Path(game.executable))
            if payload:
                self.set_cover(game,payload,report_stamp=stamp)
                return payload
        except (OSError, ValueError, struct.error):pass
        return cached

    def online_cover(self, game):
        from .artwork import resolve_cover
        from .cover_settings import load_settings
        cache = boxart_cache_directory(game.system)
        settings = load_settings()
        settings['box_3d'] = False
        # No ROM scan is needed to search artwork. A known source, when still
        # present, also permits the existing hash-aware cover services.
        rom = Path(game.source) if game.source else Path(game.title+'.rom')
        cover = resolve_cover(rom,game.title,cache,online=True,system_id=game.system,
                              settings=settings,emit=lambda _:None)
        if cover.get('style') in ('title','snapshot','box3d'):
            raise ValueError('No front cover found')
        self.set_cover(game,cover['data'],override=True,source=cover.get('source_page',''))
        return cover['data']


def pe_icon(path):
    """Read bounded PE icon resources as data, without loading the executable."""
    import mmap
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':return None
        with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
            def u16(p):return struct.unpack_from('<H',data,p)[0]
            def u32(p):return struct.unpack_from('<I',data,p)[0]
            pe = u32(60)
            if data[pe:pe+4] != b'PE\0\0':return None
            count, size = u16(pe+6), u16(pe+20)
            if count > 96:return None
            opt = pe+24
            directories = opt+(112 if u16(opt)==0x20b else 96)
            rva = u32(directories+16)
            sections = opt+size
            def offset(address):
                for i in range(count):
                    p = sections+i*40
                    virtual, start, raw, pointer = (u32(p+n) for n in (8,12,16,20))
                    if start <= address < start+min(virtual,raw):return pointer+address-start
                raise ValueError('Invalid PE resource')
            root = offset(rva)
            def entries(relative):
                p = root+relative
                n = u16(p+12)+u16(p+14)
                if n>2048:raise ValueError('Too many PE resources')
                return [(u32(p+16+i*8),u32(p+20+i*8)) for i in range(n)]
            icons = []
            for kind, directory in entries(0):
                if kind != 3 or not directory&0x80000000:continue
                for _, languages in entries(directory&0x7fffffff):
                    if not languages&0x80000000:continue
                    for _, leaf in entries(languages&0x7fffffff):
                        if leaf&0x80000000:continue
                        position = root+leaf
                        length = u32(position+4)
                        if length>8*1024*1024:continue
                        start = offset(u32(position))
                        payload = bytes(data[start:start+length])
                        if len(payload)!=length:continue
                        if payload.startswith(b'\x89PNG\r\n\x1a\n'):
                            with Image.open(BytesIO(payload)) as image:
                                icons.append((image.width*image.height,payload))
                        elif length >= 40:
                            width,height = struct.unpack_from('<ii',payload,4)
                            if 0<width<=256 and 0<height<=512:
                                header=struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',width%256,(height//2)%256,0,0,1,u16(start+14),length,22)
                                icons.append((width*height//2,header+payload))
            return max(icons,key=lambda pair:pair[0])[1] if icons else None


def elf_icon(path):
    """Recover our 256px SDL bitmap from an uncompressed ELF read-only section."""
    import mmap
    with path.open('rb') as stream:
        if stream.read(6)!=b'\x7fELF\x02\x01':return None
        with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
            section_table=struct.unpack_from('<Q',data,40)[0]
            entry_size,count=struct.unpack_from('<HH',data,58)
            if count>2048 or entry_size<64:return None
            for i in range(count):
                p=section_table+i*entry_size
                kind=struct.unpack_from('<I',data,p+4)[0]
                flags=struct.unpack_from('<Q',data,p+8)[0]
                if kind!=1 or flags&1 or not flags&2 or flags&4:continue
                start,length=struct.unpack_from('<QQ',data,p+24)
                if length>256*1024*1024 or start+length>len(data):continue
                at=start
                for _ in range(128):
                    at=data.find(b'BM',at,start+length)
                    if at<0 or at+54>start+length:break
                    size,offset=struct.unpack_from('<IxxxxI',data,at+2)
                    header,width,height,planes,bits=struct.unpack_from('<IiiHH',data,at+14)
                    if (header==40 and width==256 and height in (256,-256) and planes==1
                            and bits==32 and offset==54 and size==54+256*256*4
                            and at+size<=start+length):
                        return bytes(data[at:at+size])
                    at+=2
    return None
