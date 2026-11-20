"""Optional official cover APIs. Only clean box/front media are accepted.

ArcadeItalia's public query_mame API needs no key. It is asked only for the
arcade boards' MAME sets (a profile with `catalogues.arcadeitalia`: CPS-1,
CPS-1.5, CPS-2, Neo Geo), by the set's own name; its flyer is the cover. It is
never asked for console ROMs: a matching arcade title is not artwork for the
console version.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from PIL import Image

from . import __version__
from .cover_settings import configured
from .systems import ALL_PROFILES
from .cover_titles import clean_title, matching_indices, search_queries

PROVIDERS = {
    'screenscraper': ('ScreenScraper', 'https://www.screenscraper.fr/webapi2.php'),
    'thegamesdb': ('TheGamesDB', 'https://api.thegamesdb.net/key.php'),
    'igdb': ('IGDB', 'https://api-docs.igdb.com/#account-creation'),
    'arcadeitalia': ('ArcadeItalia', 'https://adb.arcadeitalia.net/service_scraper.php'),
}
# The platforms of each service, read from the profiles' catalogues (each checked against the service's own platform list);
# a machine whose profile gives none (0 or '') is not asked of that service.
SS_SYSTEMS = {profile.id: profile.catalogues.screenscraper for profile in ALL_PROFILES
              if profile.catalogues and profile.catalogues.screenscraper}
TGDB_SYSTEMS = {profile.id: profile.catalogues.thegamesdb for profile in ALL_PROFILES
                if profile.catalogues and profile.catalogues.thegamesdb}
IGDB_SLUGS = {profile.id: profile.catalogues.igdb for profile in ALL_PROFILES
              if profile.catalogues and profile.catalogues.igdb}
ARCADEITALIA = frozenset(profile.id for profile in ALL_PROFILES if profile.catalogues and profile.catalogues.arcadeitalia)
SERVICE_SYSTEMS = {'screenscraper': SS_SYSTEMS, 'thegamesdb': TGDB_SYSTEMS, 'igdb': IGDB_SLUGS,
                   'arcadeitalia': ARCADEITALIA}
# The order the automatic search asks the keyed services in; ArcadeItalia comes after the libretro boxes (artwork.py), so a
# home box (the Neo Geo's AES boxes) is never replaced by a flyer.
ORDER = ('screenscraper', 'thegamesdb', 'igdb')
MAME_SET = re.compile(r'[a-z0-9_]{1,40}')
# ArcadeItalia answers every image request: a set it has no flyer for gets MAME's logo (140 x 105), never a cover.
ARCADEITALIA_PLACEHOLDER = '78569f903f1b8557b205ab9e0be17309a3cad900fbfe371b64c53f0f018ee399'
ARCADEITALIA_MINIMUM_EDGE = 200
# A larger file (a disc image) is looked up on ScreenScraper by its name and size, never read whole to hash it.
SS_HASHED_BYTES = 64 * 1024 * 1024


def available(provider: str, system: str) -> bool:
    """The service knows a platform for this machine (its profile's catalogues)."""
    return system in SERVICE_SYSTEMS.get(provider, ())
REGIONS = {'eu': 'Europe', 'us': 'USA', 'jp': 'Japan', 'br': 'Brazil',
           'wor': 'World', 'kr': 'Korea'}
_locks = {name: threading.Lock() for name in PROVIDERS}
_last_request = {}
_cooldown = {}
_tokens = {}
_platforms = {}


class CoverServiceError(ValueError):
    def __init__(self, message: str, *, temporary: bool = False):
        super().__init__(message)
        self.temporary = temporary


@dataclass(frozen=True)
class RemoteCover:
    provider: str
    data: bytes
    source_page: str
    style: str  # box3d or front
    url: str | None = None  # Public only; never an authenticated media URL.


class _HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise CoverServiceError('The cover service returned an insecure redirect.')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(url: str, maximum: int, *, body: bytes | None = None,
            headers: dict | None = None, private: bool = False) -> bytes:
    """Bounded HTTPS; private curl inputs go through stdin, never argv/logs."""
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise CoverServiceError('The cover service requires HTTPS.')
    headers = {'User-Agent': f'RetroRecomp/{__version__} (box art)', **(headers or {})}
    curl = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/curl.exe'
    try:
        if os.name == 'nt' and getattr(sys, 'frozen', False) and curl.is_file():
            def quoted(value):
                return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\n', '\\n') + '"'
            config = ['url = ' + quoted(url)]
            config.extend('header = ' + quoted(f'{key}: {value}') for key, value in headers.items())
            if body is not None:
                config.append('data = ' + quoted(body.decode('utf-8')))
            args = [str(curl), '--config', '-', '--silent', '--fail', '--proto', '=https',
                    '--proto-redir', '=https', '--connect-timeout', '6', '--max-time', '12',
                    '--max-filesize', str(maximum), '--write-out', '%{http_code}']
            if not private:
                args.append('--location')
            result = subprocess.run(args, input=('\n'.join(config) + '\n').encode('utf-8'),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=14,
                creationflags=subprocess.CREATE_NO_WINDOW)
            status = int(result.stdout[-3:]) if result.stdout[-3:].isdigit() else 0
            if status in (401, 403, 429):
                raise CoverServiceError('Access refused: check API credentials or service quota.', temporary=True)
            if result.returncode or status != 200 or len(result.stdout) > maximum + 3:
                raise CoverServiceError('Cover service unavailable; check your internet connection or firewall.')
            return result.stdout[:-3]
        opener = urllib.request.build_opener(_NoRedirect() if private else _HTTPSRedirect())
        with opener.open(urllib.request.Request(url, data=body, headers=headers), timeout=8) as response:
            data = response.read(maximum + 1)
        if len(data) > maximum:
            raise CoverServiceError('The cover service response is too large.')
        return data
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status in (401, 403, 429):
            raise CoverServiceError('Access refused: check API credentials or service quota.', temporary=True) from None
        raise CoverServiceError('No usable response from the cover service.') from None
    except (OSError, urllib.error.URLError, subprocess.TimeoutExpired):
        raise CoverServiceError('Cover service unavailable; check your internet connection or firewall.') from None


# The least time between two requests to one service; ArcadeItalia is a small community site.
GAPS = {'arcadeitalia': 1.0}


def _json(provider, url, *, body=None, headers=None):
    delay = GAPS.get(provider, .30) - (time.monotonic() - _last_request.get(provider, 0))
    if delay > 0:
        time.sleep(delay)
    _last_request[provider] = time.monotonic()
    try:
        return json.loads(request(url, 2 * 1024 * 1024, body=body, headers=headers, private=True))
    except (json.JSONDecodeError, UnicodeError):
        raise CoverServiceError('The cover service returned an invalid catalogue.') from None


def _number(value):
    if isinstance(value, dict):
        value = value.get('id')
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _title(title):
    # Search text only; preserve sequel numbers and punctuation in titles.
    return clean_title(title)


def _exact(rows, field, rom_name, title, normalize):
    # Retain the adapter call signature; matching is shared with offline caches.
    rows = [row for row in rows if isinstance(row, dict)]
    indices = matching_indices([str(row.get(field, '')) for row in rows], rom_name, title)
    matches = [rows[i] for i in indices]
    unique = {str(row.get('id')): row for row in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _media_url(url: str, hosts: tuple[str, ...]) -> str:
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme not in ('http', 'https') or parts.username or parts.password
            or parts.hostname not in hosts or parts.port not in (None, 80, 443)):
        raise CoverServiceError('The cover service returned an unexpected image address.')
    return urllib.parse.urlunsplit(('https', parts.netloc.replace(':80', ''), parts.path, parts.query, ''))


def _screenscraper(account, rom, title, system, prefer3d, normalize):
    # Hashes identify a cartridge or a floppy; a disc image or a game folder is searched by its name and size only.
    size = rom.stat().st_size if rom.is_file() else 0
    params = {'devid': account['devid'], 'devpassword': account['devpassword'],
              'softname': f'RetroRecomp {__version__}', 'output': 'json',
              'systemeid': SS_SYSTEMS[system], 'romtype': 'rom', 'romnom': rom.name}
    crc = sha1 = None
    if 0 < size <= SS_HASHED_BYTES:
        payload = rom.read_bytes()
        crc = f'{zlib.crc32(payload) & 0xffffffff:08X}'
        sha1 = hashlib.sha1(payload).hexdigest()
        params.update(romtaille=len(payload), crc=crc, sha1=sha1)
    elif size:
        params['romtaille'] = size
    if account.get('ssid') and account.get('sspassword'):
        params.update(ssid=account['ssid'], sspassword=account['sspassword'])
    response = _json('screenscraper', 'https://api.screenscraper.fr/api2/jeuInfos.php?' + urllib.parse.urlencode(params))
    game = response.get('response', {}).get('jeu', {}) if isinstance(response, dict) else {}
    if not isinstance(game, dict) or _number(game.get('systeme')) != SS_SYSTEMS[system]:
        return None
    identity = game.get('rom', {})
    # Hash-confirmed ROMs may have localized game names. Otherwise require an
    # clear title match; never accept the first search result from the service.
    if not isinstance(identity, dict):
        identity = {}
    hashed = sha1 is not None and (str(identity.get('romsha1', '')).casefold() == sha1 or (
        str(identity.get('romcrc', '')).upper() == crc and _number(identity.get('romsize')) == size))
    names = game.get('noms', [])
    if isinstance(names, dict):
        names = [{'text': text} for text in names.values() if isinstance(text, str)]
    if not hashed and not matching_indices(
            [str(n.get('text', '')) for n in names if isinstance(n, dict)], rom.stem, title):
        return None
    media = game.get('medias', [])
    if isinstance(media, dict):
        # The published v2 documentation also describes nested media groups.
        def walk(node):
            for key, value in node.items():
                if isinstance(value, dict):
                    yield from walk(value)
                elif isinstance(value, str):
                    match = re.fullmatch(r'media_boitier_(3d|2d)_(\w+)', key)
                    if match:
                        yield {'type': 'box-' + match[1].upper(), 'region': match[2], 'url': value}
        media = list(walk(media))
    desired = ['box-3d', 'box-2d'] if prefer3d else ['box-2d']
    region_order = [key for key, name in REGIONS.items() if name.casefold() in rom.stem.casefold()]
    region_order += [key for key in ('wor', 'eu', 'us', 'jp') if key not in region_order]
    images = [m for m in media if isinstance(m, dict) and str(m.get('type', '')).casefold() in desired and m.get('url')]
    if not images:
        return None
    images.sort(key=lambda m: (desired.index(m['type'].casefold()),
                 region_order.index(m.get('region')) if m.get('region') in region_order else 99,
                 -((_number(m.get('width')) or 0) * (_number(m.get('height')) or 0)),
                 0 if str(m.get('format', '')).casefold() == 'png' else 1))
    chosen = images[0]
    url = _media_url(chosen['url'], ('api.screenscraper.fr', 'www.screenscraper.fr', 'screenscraper.fr'))
    # The media API's optional maxwidth/maxheight request a resized image.
    # Drop those limits to retain the service's source resolution.
    parts = urllib.parse.urlsplit(url)
    query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if key.casefold() not in ('maxwidth', 'maxheight')]
    url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    data = request(url, 8 * 1024 * 1024, private=True)
    page = 'https://www.screenscraper.fr/gameinfos.php?' + urllib.parse.urlencode({'plateforme': SS_SYSTEMS[system], 'gameid': _number(game.get('id'))})
    return RemoteCover('screenscraper', data, page, 'box3d' if chosen['type'].casefold() == 'box-3d' else 'front')


def _thegamesdb(account, rom, title, system, normalize):
    for query in search_queries(rom.stem, title):
        params = {'apikey': account['apikey'], 'name': query,
                  'filter[platform]': TGDB_SYSTEMS[system], 'include': 'boxart'}
        response = _json('thegamesdb', 'https://api.thegamesdb.net/v1.1/Games/ByGameName?' + urllib.parse.urlencode(params))
        if not isinstance(response, dict):
            return None
        rows = response.get('data', {}).get('games', [])
        rows = [r for r in rows if isinstance(r, dict) and _number(r.get('platform')) == TGDB_SYSTEMS[system]]
        game = _exact(rows, 'game_title', rom.stem, title, normalize)
        if game is not None:
            break
    else:
        return None
    boxes = response.get('include', {}).get('boxart', {})
    images = boxes.get('data', {}).get(str(game['id']), [])
    images = [i for i in images if isinstance(i, dict) and i.get('type') == 'boxart' and i.get('side') == 'front']
    if not images:
        return None
    # Multiple unidentified front editions are ambiguous; don't guess.
    if len(images) != 1:
        return None
    base = boxes.get('base_url', {}).get('original') or boxes.get('base_url', {}).get('large', '')
    url = _media_url(urllib.parse.urljoin(base, images[0]['filename']), ('cdn.thegamesdb.net',))
    return RemoteCover('thegamesdb', request(url, 8 * 1024 * 1024),
                       f"https://thegamesdb.net/game.php?id={int(game['id'])}", 'front', url)


def _igdb(account, rom, title, system, normalize):
    key = hashlib.sha256((account['client_id'] + '\0' + account['client_secret']).encode()).hexdigest()
    token, expiry = _tokens.get(key, ('', 0))
    if time.monotonic() >= expiry:
        body = urllib.parse.urlencode({'client_id': account['client_id'], 'client_secret': account['client_secret'],
                                     'grant_type': 'client_credentials'}).encode()
        response = _json('igdb', 'https://id.twitch.tv/oauth2/token', body=body,
                         headers={'Content-Type': 'application/x-www-form-urlencoded'})
        token = response.get('access_token') if isinstance(response, dict) else None
        if not token:
            raise CoverServiceError('IGDB could not obtain an application access token.', temporary=True)
        expiry = time.monotonic() + max(0, int(response.get('expires_in', 3600)) - 60)
        _tokens[key] = token, expiry
    headers = {'Client-ID': account['client_id'], 'Authorization': 'Bearer ' + token,
               'Content-Type': 'text/plain'}
    slug = IGDB_SLUGS[system]
    if slug not in _platforms:
        data = _json('igdb', 'https://api.igdb.com/v4/platforms',
                     body=f'fields id,slug; where slug = "{slug}"; limit 1;'.encode(), headers=headers)
        if not isinstance(data, list) or len(data) != 1 or data[0].get('slug') != slug:
            return None
        _platforms[slug] = int(data[0]['id'])
    platform = _platforms[slug]
    game = None
    for text in search_queries(rom.stem, title):
        query = ('fields name,url,platforms,cover.image_id; search ' + json.dumps(text) +
                 f'; where platforms = ({platform}); limit 30;')
        data = _json('igdb', 'https://api.igdb.com/v4/games', body=query.encode(), headers=headers)
        rows = [r for r in data if isinstance(r, dict) and platform in r.get('platforms', [])] if isinstance(data, list) else []
        game = _exact(rows, 'name', rom.stem, title, normalize)
        if game is not None:
            break
    image_id = game.get('cover', {}).get('image_id', '') if game else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', image_id):
        return None
    # Documented HD Fit transform preserves the full front, without cropping.
    url = f'https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg'
    page = game.get('url') or 'https://www.igdb.com/'
    page = _media_url(page, ('www.igdb.com', 'igdb.com'))
    return RemoteCover('igdb', request(url, 8 * 1024 * 1024), page, 'front', url)


def catalogue_sets(games, path: Path) -> tuple[str, ...]:
    """The MAME sets under which an arcade service files a set's art: the set the file is named after, then its parent (a clone
    shows its parent's flyer). A file that carries another name offers none, as for `cover_titles`."""
    by_set = {str(game.get('set', '')).casefold(): game for game in games if isinstance(game, dict)}
    game = by_set.get(Path(path).stem.casefold())
    if game is None:
        return ()
    parent = str(game.get('parent') or '').casefold()
    return tuple(dict.fromkeys(name for name in (str(game['set']).casefold(), parent) if name in by_set))


def cover_sets(system: str, rom: Path) -> tuple[str, ...]:
    """The machine's MAME sets for this file (an optional profile capability, `cover_sets(path)`); without one, the file's
    own name when it has a set's shape; none on failure."""
    from .systems import get_profile
    if system not in ARCADEITALIA:
        return ()
    try:
        hook = getattr(get_profile(system), 'cover_sets', None)
        names = hook(rom) if hook else (Path(rom).stem.casefold(),)
        return tuple(name for name in names if isinstance(name, str) and MAME_SET.fullmatch(name))
    except Exception:  # noqa: BLE001 - a box is never worth a failed conversion
        return ()


def _flyer(data: bytes) -> bool:
    """A real flyer: not ArcadeItalia's placeholder (MAME's logo), not a thumbnail."""
    if hashlib.sha256(data).hexdigest() == ARCADEITALIA_PLACEHOLDER:
        return False
    try:
        with Image.open(BytesIO(data)) as image:
            return max(image.size) >= ARCADEITALIA_MINIMUM_EDGE
    except (OSError, ValueError, Image.DecompressionBombError):
        return False


def _arcadeitalia(rom, title, system):
    """An arcade set's flyer from ArcadeItalia's public MAME database, asked by the set's own name, then its parent's."""
    for name in cover_sets(system, rom):
        params = {'ajax': 'query_mame', 'game_name': name, 'use_parent': 1}
        response = _json('arcadeitalia', 'https://adb.arcadeitalia.net/service_scraper.php?' + urllib.parse.urlencode(params))
        rows = response.get('result', []) if isinstance(response, dict) else []
        game = next((row for row in rows if isinstance(row, dict) and str(row.get('game_name', '')).casefold() == name), None)
        if not game or not game.get('url_image_flyer'):
            continue
        url = _media_url(game['url_image_flyer'], ('adb.arcadeitalia.net',))
        data = request(url, 8 * 1024 * 1024)
        if not _flyer(data):
            continue
        page = _media_url(game.get('url') or f'https://adb.arcadeitalia.net/?mame={name}', ('adb.arcadeitalia.net',))
        return RemoteCover('arcadeitalia', data, page, 'front', url)
    return None


def fetch(provider, account, rom: Path, title: str, system: str, *, prefer3d=False, normalize):
    if not available(provider, system) or not configured(provider, account):
        return None
    credential_id = hashlib.sha256(json.dumps(account, sort_keys=True).encode()).hexdigest()
    key = provider, credential_id
    # Each provider is serialized across concurrent conversions, including
    # ScreenScraper image fetches. Refused credentials/quotas back off in RAM.
    with _locks[provider]:
        if time.monotonic() < _cooldown.get(key, 0):
            return None
        try:
            if provider == 'screenscraper':
                return _screenscraper(account, rom, title, system, prefer3d, normalize)
            if provider == 'thegamesdb':
                return _thegamesdb(account, rom, title, system, normalize)
            if provider == 'arcadeitalia':
                return _arcadeitalia(rom, title, system)
            return _igdb(account, rom, title, system, normalize)
        except CoverServiceError as error:
            if error.temporary:
                _cooldown[key] = time.monotonic() + 300
                if provider == 'igdb':
                    _tokens.clear()
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CoverServiceError('The cover service returned incomplete metadata.') from None
