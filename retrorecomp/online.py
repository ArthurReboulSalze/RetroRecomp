"""The shared Retro-Recomp base: sign-in by e-mailed code and discovery uploads.

Only what `knowledge_exchange.write_knowledge` writes is sent: the same
ROM-free `.rrknowledge` file as a manual export (numbers and short titles, no
ROM byte, path, image or code). The account is an e-mail address proven by a
one-time code; the converter keeps a revocable token in `datas/account.json`,
which is never exported. A game is marked as shared only once the server has
accepted it, so a failed or offline upload is simply retried next time. The
server queues uploads for the maintainer, who revalidates them and only adds
discoveries to a future bundled snapshot after his own qualified conversions.

Each accepted file is followed by its claims: the short path keys of the
exact document sent (`knowledge_exchange.discovery_paths`), which give the
first finder its points at once. Before a batch, a signed-in converter also
asks the shared base for the paths other players found for the batch's ROMs
(`sync_shared`); they join the imported banks and, like any imported hint,
are checked again by every conversion. The published base (`sync_base`, no
account needed) gives the same kind of paths from an index of games and one
entry per game, fetched only for the batch's ROMs and verified by their hash;
the maintainer can revoke an upload there, and the paths it gave are withdrawn.
"""
from __future__ import annotations

import gzip
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from . import __version__

# RETRO_RECOMP_SERVICE=<base URL> points a test converter at another server
# (an empty value turns the service off).
DEFAULT_SERVICE = 'https://retro-recomp.com'
API_PATH = '/api/v1/'
ANSWER_LIMIT = 1024 * 1024
UPLOAD_LIMIT = 8 * 1024 * 1024
# The service refuses files above 16 MiB once decompressed; larger sends
# are split by game, with room left for the file's own wrapping.
PART_BYTES = 12 * 1024 * 1024
ACCOUNT_NAME = 'account.json'
# Shared-base fetches: at most FETCH_BATCH ROMs per call, answers gzipped by
# the server and bounded once decompressed (records stay small numbers). One
# answer carries at most FETCH_ROM_RECORDS stored records per ROM: a ROM that
# comes back full is asked again from its new cursor, FETCH_ROUNDS times at most.
FETCH_BATCH = 128
FETCH_LIMIT = 96 * 1024 * 1024
FETCH_ROM_RECORDS = 64
FETCH_ROUNDS = 10
# Claims: at most CLAIM_GAMES games and about CLAIM_BYTES of JSON per call
# (the service stops at 8 MiB), gzipped above GZIP_BODY; claims that could
# not be delivered wait in CLAIMS_NAME (at most CLAIMS_KEPT files).
CLAIM_GAMES = 4096
CLAIM_BYTES = 6 * 1024 * 1024
GZIP_BODY = 1024 * 1024
CLAIMS_NAME = 'account-claims.json'
CLAIMS_KEPT = 64
CURSORS_NAME = 'shared-cursors.json'
_ROM_KEY = re.compile(r'(sms|gg|gb|nes|md|snes):[0-9a-f]{64}')


class ServiceConnectionError(Exception):
    """The service could not be reached through the current network."""


class ServiceError(Exception):
    """The service answered with an error; `reason` is its stable code and
    `detail` the short text some errors carry (the minimum converter version
    of a 426 `converter_outdated`)."""

    def __init__(self, status: int, reason: str, detail: str = ''):
        super().__init__(reason)
        self.status = status
        self.reason = reason
        self.detail = detail


def _local_host(host: str) -> bool:
    """A test service on this computer or the home network may skip TLS."""
    import ipaddress
    host = (host or '').strip('[]').lower()
    if host == 'localhost' or host.endswith(('.localhost', '.test', '.local', '.lan')):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def service_url() -> str:
    """The service's base URL: https, or plain http only for a local test host."""
    from urllib.parse import urlsplit
    value = os.environ.get('RETRO_RECOMP_SERVICE', DEFAULT_SERVICE).strip().rstrip('/')
    try:
        parts = urlsplit(value)
    except ValueError:
        return ''
    if parts.scheme == 'https' and parts.hostname:
        return value
    if parts.scheme == 'http' and parts.hostname and _local_host(parts.hostname):
        return value
    return ''


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The token never follows a redirect, to the same host or another one."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def sending_available() -> bool:
    return bool(service_url())


def _account_path() -> Path:
    from .paths import data_directory
    return data_directory() / ACCOUNT_NAME


def account() -> dict | None:
    """The signed-in account of this converter for the current service."""
    try:
        data = json.loads(_account_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get('service') != service_url() or not service_url()
            or not isinstance(data.get('token'), str) or not data['token'].startswith('rr1_')):
        return None
    return data


def _save_account(data: dict | None) -> None:
    path = _account_path()
    if data is None:
        path.unlink(missing_ok=True)
        _forget_player()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates the file readable by its owner only on POSIX.
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=1, sort_keys=True)
        _owner_only(temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _owner_only(path: str) -> None:
    """On Windows the token file would inherit the folder's permissions:
    keep it to the current user (best effort; the token stays revocable)."""
    if os.name != 'nt':
        return
    import subprocess
    user = os.environ.get('USERNAME')
    if not user:
        return
    try:
        subprocess.run(['icacls', path, '/inheritance:r', '/grant:r', f'{user}:F'], check=False, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        pass


def _call(method: str, route: str, *, payload: dict | None = None, body: bytes | None = None,
          token: str | None = None, timeout: int = 20, limit: int = ANSWER_LIMIT,
          compressed: bool = False, pack: bool | int = False, download: bool = False) -> tuple[int, dict]:
    """One API request. `compressed` asks for a gzipped answer; `limit`
    bounds the answer read and, once decompressed, the JSON parsed. With
    `pack`, a JSON body above GZIP_BODY (or above the size `pack` gives)
    leaves gzipped. With `download`, a successful answer is a file kept as it was
    served ({'bytes': ...}, at most `limit` of them); errors are still JSON."""
    base = service_url()
    if not base:
        raise ServiceError(0, 'unavailable')
    headers = {'User-Agent': f'RetroRecomp/{__version__}', 'Accept': 'application/json'}
    if compressed:
        headers['Accept-Encoding'] = 'gzip'
    if payload is not None:
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        if pack and len(body) > (GZIP_BODY if pack is True else pack):
            body = gzip.compress(body, mtime=0)
            headers['Content-Encoding'] = 'gzip'
    elif body is not None:
        headers['Content-Type'] = 'application/gzip'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(base + API_PATH + route, data=body, method=method, headers=headers)
    try:
        response = _OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    except OSError as error:
        raise ServiceConnectionError() from error
    try:
        with response:
            raw = response.read(limit + 1)
            status = response.status if hasattr(response, 'status') else response.code
            encoding = str((response.headers or {}).get('Content-Encoding') or '').strip().lower()
    except (OSError, http.client.IncompleteRead) as error:
        raise ServiceConnectionError() from error
    if download and status < 400:
        if len(raw) > limit:
            raise ServiceError(status, 'bad_answer')
        return status, {'bytes': raw}
    if encoding == 'gzip' and len(raw) <= limit:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(limit + 1)
        except (OSError, EOFError):
            raw = b''
    try:
        answer = json.loads(raw) if len(raw) <= limit else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise ServiceError(status, 'bad_answer')
    if status >= 400:
        reason, detail = answer.get('error'), answer.get('detail')
        raise ServiceError(status, reason if isinstance(reason, str) else 'error',
                           detail[:200] if isinstance(detail, str) else '')
    return status, answer


def status() -> dict:
    return _call('GET', 'status')[1]


_VERSION = re.compile(r'\d{1,4}\.\d{1,4}\.\d{1,4}')


def minimum_converter(error: ServiceError | None = None, ask: bool = True) -> str:
    """The oldest Retro-Recomp version the service accepts uploads from, as
    `x.y.z`, or '' when unknown: the `detail` of a 426 `converter_outdated`,
    else (with `ask`) `min_converter` of `GET status`: one short request,
    never an error."""
    detail = (getattr(error, 'detail', '') or '').strip()
    if _VERSION.fullmatch(detail):
        return detail
    if not ask:
        return ''
    try:
        value = _call('GET', 'status', timeout=5)[1].get('min_converter')
    except (ServiceError, ServiceConnectionError):
        return ''
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else ''


def profile() -> dict | None:
    """The signed-in player's account view (pseudonym, avatar state); None
    when this converter is not signed in."""
    current = account()
    if not current:
        return None
    try:
        return _call('GET', 'account', token=current['token'])[1]
    except ServiceError as error:
        if error.status == 401:
            _save_account(None)
        raise


def avatar(limit: int = 2 * 1024 * 1024) -> bytes | None:
    """The player's own portrait as the server re-encoded it (WebP, 256 px):
    public as soon as it is sent (the maintainer moderates afterwards), or a
    legacy pending one; None without an account or a portrait."""
    current = account()
    if not current:
        return None
    request = urllib.request.Request(service_url() + API_PATH + 'account/avatar', headers={
        'User-Agent': f'RetroRecomp/{__version__}', 'Authorization': f"Bearer {current['token']}"})
    try:
        with _OPENER.open(request, timeout=20) as response:
            if response.headers.get_content_type() != 'image/webp':
                return None
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return None
    except (OSError, http.client.IncompleteRead) as error:
        raise ServiceConnectionError() from error
    return raw if 0 < len(raw) <= limit else None


def board(period: str = 'all') -> dict:
    """The public leaderboard; with an account, `you` holds the player's own
    rank, total and pending paths. `demo` is true while the board previews."""
    current = account()
    period = 'month' if period == 'month' else 'all'
    answer = _call('GET', f'board?period={period}', token=current['token'] if current else None)[1]
    entries = answer.get('entries')
    answer['entries'] = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    return answer


# The header's player corner is kept locally: opening the converter shows the
# last portrait and score without a request. Profile and score are refreshed
# when the converter starts or its window comes back to the front, at most
# every PLAYER_REFRESH seconds (and at once after a sign-in or a send), so a
# purchase, an equipped item or a portrait changed on the site shows within
# minutes for two small requests (GET account and the cached GET board). The
# portrait is downloaded again only when its public file name changes.
PLAYER_NAME = 'account-player.json'
AVATAR_NAME = 'account-avatar.webp'
PLAYER_REFRESH = 2 * 60


def _player_path() -> Path:
    return _account_path().with_name(PLAYER_NAME)


def _avatar_path() -> Path:
    return _account_path().with_name(AVATAR_NAME)


def _forget_player() -> None:
    _player_path().unlink(missing_ok=True)
    _avatar_path().unlink(missing_ok=True)


def cached_player() -> dict | None:
    """The last profile, board place and portrait of the signed-in account,
    read from disk only; None when there is none for this account."""
    current = account()
    if not current:
        return None
    try:
        data = json.loads(_player_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get('service') != current['service']
            or data.get('email') != current.get('email')):
        return None
    avatar_bytes = None
    if data.get('avatar_url'):
        try:
            avatar_bytes = _avatar_path().read_bytes()
        except OSError:
            avatar_bytes = None
    profile = data.get('profile') or {}
    catalog = cached_shop()
    return {'account': current, 'profile': profile, 'board': data.get('board') or {},
            'avatar': avatar_bytes, 'fetched': data.get('fetched', 0), 'shop': catalog,
            'frame': frame_picture(looks(catalog, equipped(profile))['frame'], download=False)}


def player(force: bool = False, now: float | None = None) -> dict | None:
    """Profile, portrait and board place for the header. Within PLAYER_REFRESH
    of the last fetch, and unless `force`, nothing goes to the network."""
    import time
    now = time.time() if now is None else now
    cached = cached_player()
    if cached and not force and 0 <= now - cached['fetched'] < PLAYER_REFRESH:
        return cached
    current = account()
    if not current:
        return None
    details = profile() or {}
    you = board('all').get('you') or {}
    url = (details.get('avatar') or {}).get('url')
    picture = cached['avatar'] if cached and cached['avatar'] and url and _cached_avatar_url() == url else None
    if url and picture is None:
        picture = avatar()
        if picture:
            _write_bytes(_avatar_path(), picture)
    if not url:
        _avatar_path().unlink(missing_ok=True)
    record = {'service': current['service'], 'email': current.get('email'), 'fetched': now,
              'profile': details, 'board': {'you': you}, 'avatar_url': url if picture else None}
    _write_bytes(_player_path(), json.dumps(record, indent=1, sort_keys=True).encode('utf-8'))
    # The shop's catalog follows the player (at most every SHOP_REFRESH); the
    # equipped frame's image is downloaded once.
    catalog = shop(now=now)
    frame = frame_picture(looks(catalog, equipped(details))['frame'])
    return {'account': current, 'profile': details, 'board': {'you': you}, 'avatar': picture, 'fetched': now,
            'shop': catalog, 'frame': frame}


# The RR coin shop (1.5.2) is cosmetic and its purchases happen on the site:
# the converter only draws what the account equips (`items` and `equipped` of
# the account view, kept with the player corner). The public catalog (`GET
# shop`) is cached beside it and refreshed with the player, at most every
# PLAYER_REFRESH; a frame's image is downloaded once, then read from `datas/`.
# Without a catalog (offline, older server) nothing extra is drawn.
SHOP_NAME = 'shop-catalog.json'
FRAME_PREFIX = 'shop-frame-'
FRAME_LIMIT = 1024 * 1024
FRAME_TYPES = {'image/webp': '.webp', 'image/png': '.png'}
SHOP_SLOTS = ('title', 'name_style', 'background', 'hover', 'header_theme', 'pin', 'frame')
SHOP_BADGES = 3
# The catalog changes only with the site's releases: kept half an hour.
SHOP_REFRESH = 30 * 60
_MEDIA_PATH = re.compile(r'/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*')


def _shop_path() -> Path:
    return _account_path().with_name(SHOP_NAME)


def _catalog(items) -> dict:
    """{id: item} from the `items` of `GET shop`, malformed entries left out."""
    catalog = {}
    for item in items if isinstance(items, list) else ():
        if (isinstance(item, dict) and isinstance(item.get('id'), str) and isinstance(item.get('slot'), str)
                and item['id'] not in catalog):
            data = item.get('data')
            catalog[item['id']] = {**item, 'data': data if isinstance(data, dict) else {}}
    return catalog


def _shop_record() -> dict | None:
    try:
        data = json.loads(_shop_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not service_url() or data.get('service') != service_url():
        return None
    return data


def cached_shop() -> dict:
    """The last catalog of this service, {id: item}, read from disk only."""
    record = _shop_record()
    return _catalog(record.get('items')) if record else {}


def shop(force: bool = False, now: float | None = None) -> dict:
    """The shop's catalog {id: item}: the cached one within SHOP_REFRESH,
    else `GET shop` (public, no token). A server without the shop leaves an
    empty catalog until the next refresh; offline, the last one stays."""
    import time
    now = time.time() if now is None else now
    record = _shop_record()
    try:
        fetched = float(record.get('fetched') or 0) if record else 0.0
    except (TypeError, ValueError):
        fetched = 0.0
    if record and not force and 0 <= now - fetched < SHOP_REFRESH:
        return _catalog(record.get('items'))
    try:
        items = _call('GET', 'shop', timeout=10)[1].get('items')
    except ServiceConnectionError:
        return _catalog(record.get('items')) if record else {}
    except ServiceError as error:
        if error.reason == 'unavailable':
            return {}
        items = []
    catalog = _catalog(items)
    try:
        _write_bytes(_shop_path(), json.dumps({'service': service_url(), 'fetched': now, 'items': list(catalog.values())},
                                              indent=1, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    except OSError:
        pass
    _prune_frames(catalog)
    return catalog


# The games someone already completed at the Thorough level (GET explored, a
# small public answer the server reads from its all-time board cache), for
# Compiled Games' "Games to explore" filter: kept SHOP_REFRESH, then asked
# again when the filter is used. The first player to complete a game at the
# Thorough level earns the explorer coins (`explorer`).
EXPLORED_NAME = 'shared-explored.json'
EXPLORED_LIMIT = 4 * 1024 * 1024


def _explored_view(record) -> dict:
    record = record if isinstance(record, dict) else {}
    games = record.get('games') if isinstance(record.get('games'), dict) else {}
    depth = record.get('depth') if isinstance(record.get('depth'), dict) else {}
    explorer = record.get('explorer')
    return {'games': {key: (value.get('by') if isinstance(value, dict) and isinstance(value.get('by'), str) else None)
                      for key, value in games.items() if isinstance(key, str) and _ROM_KEY.fullmatch(key)},
            'explorer': explorer if type(explorer) is int else None,
            'depth': {level: value for level, value in depth.items() if level in ('extended', 'thorough') and type(value) is int},
            'fetched': record.get('fetched', 0)}


def explored(force: bool = False, now: float | None = None) -> dict:
    """{'games': {'sms:<identity>': first explorer's name or None}, 'explorer':
    coins or None, 'depth': {'extended', 'thorough'}}: cached SHOP_REFRESH;
    offline, the last answer; a server without it, nothing explored."""
    import time
    now = time.time() if now is None else now
    path = _account_path().with_name(EXPLORED_NAME)
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        record = record if isinstance(record, dict) and record.get('service') == service_url() else None
    except (OSError, ValueError):
        record = None
    try:
        fetched = float(record.get('fetched') or 0) if record else 0.0
    except (TypeError, ValueError):
        fetched = 0.0
    if record and not force and 0 <= now - fetched < SHOP_REFRESH:
        return _explored_view(record)
    try:
        answer = _call('GET', 'explored', timeout=10, limit=EXPLORED_LIMIT, compressed=True)[1]
    except ServiceConnectionError:
        return _explored_view(record)
    except ServiceError as error:
        if error.reason == 'unavailable':
            return _explored_view(None)
        answer = {}
    view = _explored_view(answer)
    # Stored in the server's shape, read back by _explored_view.
    record = {'games': {key: {'by': name} for key, name in view['games'].items()}, 'explorer': view['explorer'],
              'depth': view['depth'], 'service': service_url(), 'fetched': now}
    try:
        _write_bytes(path, json.dumps(record, sort_keys=True).encode('utf-8'))
    except OSError:
        pass
    return _explored_view(record)


def equipped(profile) -> dict:
    """The equipped ids of an account view or a board entry: one id (or None)
    per slot and up to SHOP_BADGES `badges`."""
    source = profile.get('equipped') if isinstance(profile, dict) else None
    source = source if isinstance(source, dict) else {}
    view = {slot: source.get(slot) if isinstance(source.get(slot), str) else None for slot in SHOP_SLOTS}
    badges = source.get('badges')
    view['badges'] = [value for value in badges if isinstance(value, str)][:SHOP_BADGES] if isinstance(badges, list) else []
    return view


def top_badges(profile) -> list:
    """The badges of the consoles where the player is first on the all-time
    board (`top_badges` since 26 October 2026; absent before): a first-place badge is
    drawn with its mark."""
    values = profile.get('top_badges') if isinstance(profile, dict) else None
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def queued_conversions(profile) -> tuple:
    """(games, days): the converted games beyond the service's daily bound that
    wait for their reward, and in how many days the last one is credited
    (`conversions.queued` / `queued_days` of the account view since 26 October
    2026; (0, 0) from an older service)."""
    conversions = profile.get('conversions') if isinstance(profile, dict) else None
    conversions = conversions if isinstance(conversions, dict) else {}
    count, days = conversions.get('queued'), conversions.get('queued_days')
    return (count if type(count) is int and count > 0 else 0,
            days if type(days) is int and days > 0 else 0)


def pseudonym_chosen(profile) -> bool:
    """False while the account shows a pseudonym the server generated (the
    player is asked to choose one); true for older servers that do not say."""
    return not (isinstance(profile, dict) and profile.get('pseudonym_chosen') is False)


def owned(profile) -> list:
    """The shop items the account owns (`items` of the account view)."""
    items = profile.get('items') if isinstance(profile, dict) else None
    return [value for value in items if isinstance(value, str)] if isinstance(items, list) else []


def looks(catalog: dict, view: dict) -> dict:
    """The catalog items behind equipped ids, each kept only in its own slot:
    {slot: item | None, 'badges': [items]}. Unknown ids draw nothing."""
    catalog = catalog if isinstance(catalog, dict) else {}
    view = view if isinstance(view, dict) else {}
    def item(identifier, slot):
        found = catalog.get(identifier) if isinstance(identifier, str) else None
        return found if isinstance(found, dict) and found.get('slot') == slot else None
    result = {slot: item(view.get(slot), slot) for slot in SHOP_SLOTS}
    badges = view.get('badges') if isinstance(view.get('badges'), list) else []
    result['badges'] = [found for found in (item(identifier, 'badge') for identifier in badges) if found][:SHOP_BADGES]
    return result


def _media_url(value) -> str | None:
    """A picture of the catalog on the service itself (a path of the site, or
    an absolute URL under the service's own address); None otherwise."""
    base = service_url()
    if not base or not isinstance(value, str):
        return None
    if value.startswith(base + '/'):
        value = value[len(base):]
    return base + value if _MEDIA_PATH.fullmatch(value) and '..' not in value else None


def _frame_path(url: str) -> Path:
    import hashlib
    suffix = '.png' if url.lower().endswith('.png') else '.webp'
    return _account_path().with_name(FRAME_PREFIX + hashlib.sha256(url.encode('utf-8')).hexdigest()[:20] + suffix)


def _prune_frames(catalog: dict) -> None:
    """Frame pictures the catalog no longer names are deleted."""
    kept = {_frame_path(url).name for url in (_media_url((item.get('data') or {}).get('image'))
                                              for item in catalog.values() if item.get('slot') == 'frame') if url}
    try:
        stale = [path for path in _account_path().parent.glob(FRAME_PREFIX + '*') if path.name not in kept]
    except OSError:
        return
    for path in stale:
        try:
            path.unlink()
        except OSError:
            pass


def frame_picture(item, download: bool = True) -> bytes | None:
    """The image of a frame item (WebP or PNG from the site), cached in
    `datas/` once downloaded; None without one, or on any failure (a frame is
    decoration, never an error)."""
    data = item.get('data') if isinstance(item, dict) and item.get('slot') == 'frame' else None
    url = _media_url(data.get('image')) if isinstance(data, dict) else None
    if not url:
        return None
    path = _frame_path(url)
    try:
        cached = path.read_bytes()
        if 0 < len(cached) <= FRAME_LIMIT:
            return cached
    except OSError:
        pass
    if not download:
        return None
    request = urllib.request.Request(url, headers={'User-Agent': f'RetroRecomp/{__version__}'})
    try:
        with _OPENER.open(request, timeout=20) as response:
            if response.headers.get_content_type() not in FRAME_TYPES:
                return None
            raw = response.read(FRAME_LIMIT + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return None
    except (OSError, http.client.IncompleteRead, ValueError):
        return None
    if not 0 < len(raw) <= FRAME_LIMIT:
        return None
    try:
        _write_bytes(path, raw)
    except OSError:
        pass
    return raw


def _cached_avatar_url() -> str | None:
    try:
        return json.loads(_player_path().read_text(encoding='utf-8')).get('avatar_url')
    except (OSError, ValueError, AttributeError):
        return None


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def request_code(email: str, language: str = 'en') -> None:
    """E-mail a sign-in code; the player has accepted the privacy terms."""
    _call('POST', 'auth/code', payload={'email': email, 'language': language, 'accept_terms': True})


def sign_in(email: str, code: str, label: str = '', pseudonym: str | None = None) -> dict:
    """Trade the e-mailed code for this converter's token, remembered locally.
    With `pseudonym`, an account that has none yet (or only a generated one)
    takes it; a taken one raises ServiceError 409 'pseudonym_taken', the code
    still unspent. Without one, the server generates one (since 26 October 2026)."""
    payload = {'email': email, 'code': code, 'label': label[:64]}
    if pseudonym and pseudonym.strip():
        payload['pseudonym'] = pseudonym.strip()[:PSEUDONYM_LIMIT]
    answer = _call('POST', 'auth/token', payload=payload)[1]
    token, details = answer.get('token'), answer.get('account')
    if not isinstance(token, str) or not token.startswith('rr1_') or not isinstance(details, dict):
        raise ServiceError(200, 'bad_answer')
    data = {'service': service_url(), 'token': token, 'email': str(details.get('email') or email),
            'pseudonym': details.get('pseudonym') if isinstance(details.get('pseudonym'), str) else None,
            'pseudonym_chosen': pseudonym_chosen(details)}
    _save_account(data)
    return data


PSEUDONYM_LIMIT = 32
_PSEUDONYM = re.compile(r'[^\W_][\w .\-]{1,30}[^\W_]')


def suggested_pseudonym() -> str:
    """A pseudonym to propose: "RetroPlayer_" and four random digits (nothing
    about the computer or its user)."""
    import secrets
    return f'RetroPlayer_{secrets.randbelow(10000):04d}'


def valid_pseudonym(name: str) -> bool:
    """The server's rule: 3 to 32 letters, digits, spaces, '.', '_' or '-',
    starting and ending with a letter or a digit."""
    return bool(_PSEUDONYM.fullmatch(' '.join(str(name).split())))


def set_pseudonym(name: str) -> dict:
    """PATCH account {pseudonym}: the account view; ServiceError 400
    'invalid_pseudonym' or 409 'pseudonym_taken'."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    try:
        details = _call('PATCH', 'account', payload={'pseudonym': ' '.join(str(name).split())}, token=current['token'])[1]
    except ServiceError as error:
        if error.status == 401:
            _save_account(None)
        raise
    if isinstance(details.get('pseudonym'), str):
        _save_account({**current, 'pseudonym': details['pseudonym'], 'pseudonym_chosen': pseudonym_chosen(details)})
    return details


def sign_out() -> None:
    """Forget the token here; revoking it on the server is best effort."""
    current = account()
    if current:
        try:
            _call('DELETE', 'auth/token', token=current['token'], timeout=8)
        except (ServiceError, ServiceConnectionError):
            pass
    _save_account(None)


def pending(collected: dict) -> dict:
    """`collected` restricted to the games whose discoveries changed since
    they were last sent with an account, plus the games this account
    converted successfully that the service has not heard of yet
    (`note_conversion`), even without anything new: they travel as records
    without hints, at most CONVERTED_PER_SEND per send, and their claims say
    `converted` (the gift for a game the base already knew, the depth coins)."""
    from .knowledge_exchange import pending_since_shared
    keys = set(pending_since_shared('account', collected))
    return _with_conversions(_restrict(collected, keys), collected)


# --- Conversions: the games this account converted, for the conversion rewards
#
# Since 1.5.2 a game the bundled snapshot knows is rebuilt from its paths and
# brings nothing new: without a note, the service never hears of it. Each
# successful conversion made while signed in is noted here (`note_conversion`,
# called by the interface once a game is converted); the next send carries the
# noted games (a record without hints when nothing is new) and claims them as
# `converted` with their scan level. The service pays once the upload is
# checked, once per account and game (web/lib/rewards.php). A note leaves the
# queue once a file holding the game was accepted.
CONVERTED_NAME = 'account-converted.json'
CONVERTED_KEPT = 4096
CONVERTED_PER_SEND = 50
_CONVERTED_LOCK = threading.Lock()


def _converted_path() -> Path:
    return _account_path().with_name(CONVERTED_NAME)


def _converted_queue(current: dict | None = None) -> list:
    """The noted games ('system:identity') of the signed-in account, oldest first."""
    current = current or account()
    if not current:
        return []
    try:
        data = json.loads(_converted_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if (not isinstance(data, dict) or data.get('service') != current['service']
            or data.get('email') != current.get('email') or not isinstance(data.get('games'), list)):
        return []
    return [key for key in data['games'] if isinstance(key, str) and _ROM_KEY.fullmatch(key)]


def _save_converted(current: dict, games: list) -> None:
    record = {'service': current['service'], 'email': current.get('email'), 'games': games[-CONVERTED_KEPT:]}
    _write_bytes(_converted_path(), json.dumps(record, indent=1).encode('utf-8'))


def note_conversion(system: str, identity: str) -> bool:
    """Remember that this account converted this exact game successfully;
    nothing without an account or for a console the service does not take.
    Safe from several conversion threads at once. True when noted."""
    key = f'{system}:{identity}'
    current = account() if sending_available() else None
    if not current or not _ROM_KEY.fullmatch(key):
        return False
    with _CONVERTED_LOCK:
        games = [value for value in _converted_queue(current) if value != key]
        try:
            _save_converted(current, [*games, key])
        except OSError:
            return False
    return True


def noted_conversions() -> list:
    """The games noted and not sent yet."""
    return _converted_queue()


def _forget_conversions(current: dict, keys) -> None:
    keys = set(keys)
    if not keys:
        return
    with _CONVERTED_LOCK:
        try:
            _save_converted(current, [key for key in _converted_queue(current) if key not in keys])
        except OSError:
            pass


def _with_conversions(restricted: dict, collected: dict) -> dict:
    """`restricted` plus the noted games: those already in it are flagged
    converted; the others, when `collected['converted']` knows them (a
    qualified conversion with nothing new), join as records without hints."""
    noted = _converted_queue()
    if not noted:
        return restricted
    present = {f'{system}:{identity}' for system, records in restricted['payload'].get('consoles', {}).items()
               for identity in records}
    known = {f'{system}:{identity}': value for system, games in (collected.get('converted') or {}).items()
             for identity, value in games.items()}
    flagged = [key for key in noted if key in present]
    added = [key for key in noted if key not in present and key in known][:CONVERTED_PER_SEND]
    if not flagged and not added:
        return restricted
    consoles = {system: dict(records) for system, records in restricted['payload'].get('consoles', {}).items()}
    titles = {system: dict(names) for system, names in restricted.get('titles', {}).items()}
    levels = {system: dict(values) for system, values in restricted.get('levels', {}).items()}
    for key in added:
        system, identity = key.split(':', 1)
        value = known[key]
        consoles.setdefault(system, {})[identity] = {'engine': value['engine'], 'rom_bytes': value['rom_bytes']}
        titles.setdefault(system, {})[identity] = str(value.get('title') or identity[:12])
        levels.setdefault(system, {})[identity] = value.get('level') or 'standard'
    sharing = {system: len(names) for system, names in sorted(titles.items())}
    return {**restricted, 'payload': {'schema': 1, 'consoles': consoles}, 'titles': titles, 'levels': levels,
            'games': sum(sharing.values()), 'consoles': sharing, 'converted_keys': sorted({*flagged, *added})}


def _restrict(collected: dict, keys: set) -> dict:
    """`collected` limited to the games `keys` ('system:identity') name."""
    from .knowledge_exchange import _bundled, unknown_hints
    consoles, observations, titles, discoveries = {}, {}, {}, 0
    for system, records in collected['payload'].get('consoles', {}).items():
        for identity, record in records.items():
            if f'{system}:{identity}' in keys:
                consoles.setdefault(system, {})[identity] = record
                discoveries += unknown_hints(system, record, _bundled(system, identity))
    for system, games in collected.get('observations', {}).items():
        for identity, rows in games.items():
            if f'{system}:{identity}' in keys:
                observations.setdefault(system, {})[identity] = rows
                discoveries += len(rows)
    for system, names in collected.get('titles', {}).items():
        for identity, title in names.items():
            if f'{system}:{identity}' in keys:
                titles.setdefault(system, {})[identity] = title
    levels = {system: {identity: level for identity, level in values.items() if f'{system}:{identity}' in keys}
              for system, values in collected.get('levels', {}).items()}
    sharing = {system: len(names) for system, names in sorted(titles.items())}
    return {**collected, 'games': sum(sharing.values()), 'consoles': sharing, 'discoveries': discoveries,
            'observations': observations, 'titles': titles, 'levels': {s: v for s, v in levels.items() if v},
            'observation_count': sum(len(rows) for games in observations.values() for rows in games.values()),
            'payload': {'schema': 1, 'consoles': consoles}}


def _parts(collected: dict, limit: int | None = None) -> list:
    """Groups of games whose file stays under the server's decompressed
    bound; a first upload of a large collection leaves as several files."""
    limit = limit or PART_BYTES
    sizes = {}
    def add(system, identity, value):
        key = f'{system}:{identity}'
        sizes[key] = sizes.get(key, 0) + len(json.dumps(value, separators=(',', ':')))
    for system, records in collected['payload'].get('consoles', {}).items():
        for identity, record in records.items():
            add(system, identity, record)
    for system, games in collected.get('observations', {}).items():
        for identity, rows in games.items():
            add(system, identity, rows)
    for system, names in collected.get('titles', {}).items():
        for identity, title in names.items():
            add(system, identity, title)
    parts, current, size = [], set(), 0
    for key in sorted(sizes):
        if current and size + sizes[key] > limit:
            parts.append(current)
            current, size = set(), 0
        current.add(key)
        size += sizes[key]
    if current:
        parts.append(current)
    return parts


def send(collected: dict) -> dict:
    """Upload what `pending` kept, as `.rrknowledge` files under the server's
    bound; each accepted file marks its games as shared on the 'account'
    channel, so an interrupted send resumes with the games still pending.
    Claims that an earlier send could not deliver go first; `claims` in the
    result sums the server's answers (None when it answered none) and
    `claims_refused` names why the service refused some for good."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    answer, refused = _retry_claims()
    answers = [answer]
    def finish(result):
        return {**result, 'claims': _claims_total(answers), 'claims_refused': sorted(set(refused))}
    if not collected['games']:
        return finish({'games': 0, 'discoveries': 0})
    parts = _parts(collected)
    if len(parts) == 1:
        result = _send_one(collected, current)
        answers.append(result.pop('claims'))
        refused.extend(filter(None, [result.pop('claims_refused')]))
        return finish(result)
    total = {'games': 0, 'discoveries': 0, 'bytes': 0, 'files': 0, 'duplicate': True}
    for keys in parts:
        result = _send_one(_restrict(collected, keys), current)
        answers.append(result.get('claims'))
        refused.extend(filter(None, [result.get('claims_refused')]))
        total['games'] += result['games']
        total['discoveries'] += result['discoveries']
        total['bytes'] += result['bytes']
        total['files'] += 1
        total['duplicate'] = total['duplicate'] and result['duplicate']
        total['id'] = result.get('id')
    return finish(total)


def _send_one(collected: dict, current: dict) -> dict:
    from .knowledge_exchange import discovery_paths, mark_shared, read_exchange, write_knowledge
    from .paths import data_directory
    folder = data_directory() / 'knowledge'
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='upload-', suffix='.rrknowledge', dir=folder)
    os.close(fd)
    try:
        write_knowledge(collected, Path(name), channel=None)
        body = Path(name).read_bytes()
        # The claims name the paths of this exact file, read back as the
        # maintainer's validation reads it.
        paths = discovery_paths(read_exchange(Path(name)))
    finally:
        os.unlink(name)
    if len(body) > UPLOAD_LIMIT:
        raise ServiceError(413, 'too_large')
    try:
        code, answer = _call('POST', 'contributions', body=body, token=current['token'], timeout=60)
    except ServiceError as error:
        if error.status == 401:
            _save_account(None)   # revoked or deleted elsewhere: sign in again
        elif error.reason == 'converter_outdated':
            error.detail = minimum_converter(error)
        raise
    mark_shared('account', collected)
    converted = set(collected.get('converted_keys') or ()) & {
        f'{system}:{identity}' for system, records in collected['payload'].get('consoles', {}).items() for identity in records}
    _forget_conversions(current, converted)
    # The scan level of each qualified game rides beside the file (which
    # keeps its format), in the claims; losing it only costs the scan bonus.
    levels = {f'{system}:{identity}': level for system, values in collected.get('levels', {}).items()
              for identity, level in values.items()}
    contribution, claimed, refused = answer.get('id'), None, None
    games = claim_games(paths, levels, converted)
    # 201: a new file; 200: this account's earlier copy, whose claims are idempotent.
    if isinstance(contribution, int) and code in (200, 201) and games:
        claimed, refused = _deliver_claims(contribution, games, levels if code == 201 else {}, current)
    return {'games': collected['games'], 'discoveries': collected['discoveries'], 'bytes': len(body),
            'id': contribution, 'duplicate': bool(answer.get('duplicate')) or code == 200, 'claims': claimed,
            'claims_refused': refused}


# --- Claims: the paths each accepted file brings, for immediate points -----

def claim_games(paths: dict, levels: dict, converted=()) -> list:
    """The claims body's games, from `discovery_paths` of the uploaded file.
    A game without a qualified conversion (raw observations only) counts at
    the standard level, as before scan levels were sent. The games of
    `converted` ('system:identity') say so, with or without paths."""
    converted = set(converted)
    games = []
    for (system, identity), value in sorted(paths.items()):
        done = f'{system}:{identity}' in converted
        if not (value['hints'] or value['observations'] or done):
            continue
        game = {'system': system, 'identity': identity, 'known': bool(value['known']),
                'level': levels.get(f'{system}:{identity}', 'standard'),
                'hints': list(value['hints']), 'observations': list(value['observations'])}
        if done:
            game['converted'] = True
        games.append(game)
    return games


def _claim_parts(games: list):
    """Games in groups of at most CLAIM_GAMES and about CLAIM_BYTES of JSON;
    each game appears once, in one group."""
    part, size = [], 0
    for game in games:
        cost = len(json.dumps(game, separators=(',', ':'))) + 1
        if part and (len(part) >= CLAIM_GAMES or size + cost > CLAIM_BYTES):
            yield part
            part, size = [], 0
        part.append(game)
        size += cost
    if part:
        yield part


def claims(contribution: int, games: list) -> dict:
    """POST contributions/{id}/claims, in groups under the service's bounds
    (gzipped when large); the sum of the answers ({'games', 'paths', 'new'}).
    Raises like `_call`."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    total = {'games': 0, 'paths': 0, 'new': 0, 'converted': 0}
    for part in _claim_parts(games):
        try:
            answer = _call('POST', f'contributions/{int(contribution)}/claims', token=current['token'],
                           timeout=60, payload={'games': part}, pack=True)[1]
        except ServiceError as error:
            if error.status == 401:
                _save_account(None)
            raise
        for name in total:
            value = answer.get(name)
            total[name] += value if type(value) is int and value >= 0 else 0
    if not total['converted']:
        del total['converted']   # a server before 26 October 2026, or no game noted
    return total


def _retryable(error: ServiceError) -> bool:
    """Claims refused for a reason that may pass (busy, rate-limited, signed
    out); a malformed or forbidden claim is dropped."""
    return error.status in (401, 408, 425, 429) or error.status >= 500 or error.reason == 'bad_answer'


def _deliver_claims(contribution: int, games: list, levels: dict, current: dict) -> tuple:
    """(answer or None, reason the service refused them or None)."""
    try:
        return claims(contribution, games), None
    except ServiceError as error:
        if error.status == 404:
            # A server without claims: only the scan levels, as 1.5.0 sent them.
            if levels:
                try:
                    _call('POST', f'contributions/{contribution}/levels', payload={'levels': levels},
                          token=current['token'])
                except (ServiceError, ServiceConnectionError):
                    pass
        elif _retryable(error):
            _queue_claims(contribution, games, current)
        else:
            # Refused for good (the file was found invalid, or a malformed claim).
            return None, error.reason
    except ServiceConnectionError:
        _queue_claims(contribution, games, current)
    return None, None


def _claims_path() -> Path:
    return _account_path().with_name(CLAIMS_NAME)


def _waiting_claims() -> list:
    try:
        data = json.loads(_claims_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [entry for entry in data if isinstance(entry, dict) and type(entry.get('id')) is int
            and isinstance(entry.get('games'), list)] if isinstance(data, list) else []


def _keep_claims(entries: list) -> None:
    if entries:
        _write_bytes(_claims_path(), json.dumps(entries[-CLAIMS_KEPT:], separators=(',', ':')).encode('utf-8'))
    else:
        _claims_path().unlink(missing_ok=True)


def _queue_claims(contribution: int, games: list, current: dict) -> None:
    owner = (current['service'], current.get('email'))
    entries = [entry for entry in _waiting_claims()
               if not ((entry.get('service'), entry.get('email')) == owner and entry['id'] == contribution)]
    entries.append({'service': owner[0], 'email': owner[1], 'id': contribution, 'games': games})
    try:
        _keep_claims(entries)
    except OSError:
        pass


def waiting_claims() -> int:
    """Accepted files of this account whose claims still wait for delivery."""
    current = account()
    if not current:
        return 0
    owner = (current['service'], current.get('email'))
    return sum((entry.get('service'), entry.get('email')) == owner for entry in _waiting_claims())


def retry_claims() -> dict | None:
    """Deliver the claims an earlier send could not; those still refused for
    a passing reason wait again. The answers' sum, or None if none answered."""
    return _retry_claims()[0]


def _retry_claims() -> tuple:
    """(answers' sum or None, reasons of the claims refused for good)."""
    current = account()
    entries = _waiting_claims()
    if not current or not entries:
        return None, []
    owner = (current['service'], current.get('email'))
    kept, answers, refused, offline = [], [], [], False
    for entry in entries:
        if offline or (entry.get('service'), entry.get('email')) != owner:
            kept.append(entry)
            continue
        try:
            answers.append(claims(entry['id'], entry['games']))
        except ServiceError as error:
            if _retryable(error):
                kept.append(entry)
            elif error.status != 404:
                refused.append(error.reason)
        except ServiceConnectionError:
            kept.append(entry)
            offline = True
    try:
        _keep_claims(kept)
    except OSError:
        pass
    return _claims_total(answers), refused


def _claims_total(answers) -> dict | None:
    answered = [answer for answer in answers if answer]
    if not answered:
        return None
    names = ('games', 'paths', 'new', *(('converted',) if any(answer.get('converted') for answer in answered) else ()))
    return {name: sum(answer.get(name, 0) for answer in answered) for name in names}


# --- Shared-base sync: the paths other players found, before a batch -------

def _cursor_value(value) -> int:
    return value if type(value) is int and value >= 0 else 0


def _rom_keys(values) -> list:
    return sorted({key for key in values if isinstance(key, str) and _ROM_KEY.fullmatch(key)})


def fetch_knowledge(rom_keys, cursors: dict | None = None) -> dict:
    """POST knowledge/fetch for `rom_keys` ('system:sha256'), FETCH_BATCH ROMs
    per call, each with the last cursor received for it (0 at first). Returns
    {'roms': {key: {'cursor', 'level', 'records', 'observations'}}} for the
    ROMs with something newer than their cursor."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    keys = _rom_keys(rom_keys)
    cursors = {key: _cursor_value((cursors or {}).get(key)) for key in keys}
    served, asked = {}, keys
    for _ in range(FETCH_ROUNDS):
        full = []
        for start in range(0, len(asked), FETCH_BATCH):
            chunk = asked[start:start + FETCH_BATCH]
            try:
                answer = _call('POST', 'knowledge/fetch', token=current['token'], timeout=120, limit=FETCH_LIMIT,
                               compressed=True, payload={'roms': {key: cursors[key] for key in chunk}})[1]
            except ServiceError as error:
                if error.status == 401:
                    _save_account(None)
                raise
            roms = answer.get('roms')
            if roms == []:
                roms = {}   # an empty JSON object may come back as an empty list
            if not isinstance(roms, dict):
                raise ServiceError(200, 'bad_answer')
            for key in set(chunk) & set(roms):
                value = roms[key]
                if not isinstance(value, dict):
                    continue
                served[key] = _served_together(served.get(key), value)
                cursor, records = value.get('cursor'), value.get('records')
                # A full answer for this ROM: newer records may wait behind it.
                if (type(cursor) is int and cursor > cursors[key] and isinstance(records, list)
                        and len(records) >= FETCH_ROM_RECORDS):
                    cursors[key] = cursor
                    full.append(key)
        if not full:
            break
        asked = sorted(full)
    return {'roms': served}


def _served_together(earlier: dict | None, later: dict) -> dict:
    """One ROM's answers over several rounds: records and rows in order, the
    highest cursor, and the best level (each answer names its own best)."""
    from .scan_levels import LEVELS
    if earlier is None:
        return dict(later)
    rows = lambda value, name: value.get(name) if isinstance(value.get(name), list) else []
    cursors = [value.get('cursor') for value in (earlier, later) if type(value.get('cursor')) is int]
    levels = [value.get('level') for value in (earlier, later) if value.get('level') in LEVELS]
    return {'cursor': max(cursors) if cursors else None,
            'level': max(levels, key=LEVELS.index) if levels else None,
            'records': rows(earlier, 'records') + rows(later, 'records'),
            'observations': rows(earlier, 'observations') + rows(later, 'observations')}


def _cursors_path() -> Path:
    # Beside the imported banks: removing them also restarts the sync.
    from .knowledge import imported_path
    return imported_path().with_name(CURSORS_NAME)


def _shared_state(current: dict) -> dict:
    """{key: {'cursor', 'level', 'records'}} kept for this account."""
    try:
        data = json.loads(_cursors_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if (not isinstance(data, dict) or data.get('service') != current['service']
            or data.get('email') != current.get('email') or not isinstance(data.get('roms'), dict)):
        return {}
    return {key: dict(value) for key, value in data['roms'].items()
            if isinstance(key, str) and _ROM_KEY.fullmatch(key) and isinstance(value, dict)}


def _save_shared_state(current: dict, state: dict) -> None:
    data = {'service': current['service'], 'email': current.get('email'), 'roms': dict(sorted(state.items()))}
    _write_bytes(_cursors_path(), (json.dumps(data, indent=1, sort_keys=True) + '\n').encode('utf-8'))


def sync_shared(rom_keys) -> dict:
    """One fetch for these ROMs: what arrives joins the imported banks (as an
    imported file would), then each ROM's cursor moves on and the best scan
    level received with valid paths is kept. Counts for the log."""
    from .knowledge_exchange import import_fetched
    from .scan_levels import LEVELS
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    keys = _rom_keys(rom_keys)
    summary = {'asked': len(keys), 'roms': 0, 'records': 0, 'observations': 0, 'new': 0, 'enriched': 0}
    if not keys:
        return summary
    state = _shared_state(current)
    answer = fetch_knowledge(keys, {key: state.get(key, {}).get('cursor') for key in keys})
    if not answer['roms']:
        return summary
    outcome = import_fetched(answer['roms'])
    for key, value in answer['roms'].items():
        entry = state.setdefault(key, {})
        cursor = value.get('cursor')
        if type(cursor) is int and cursor > _cursor_value(entry.get('cursor')):
            entry['cursor'] = cursor
        accepted = outcome['accepted'].get(key) or {}
        if not (accepted.get('records') or accepted.get('observations')):
            continue
        entry['records'] = _cursor_value(entry.get('records')) + accepted.get('records', 0)
        level = value.get('level')
        if level in LEVELS and (entry.get('level') not in LEVELS
                                or LEVELS.index(level) > LEVELS.index(entry['level'])):
            entry['level'] = level
        summary['roms'] += 1
        summary['records'] += accepted.get('records', 0)
        summary['observations'] += accepted.get('observations', 0)
    _save_shared_state(current, state)
    summary.update(new=outcome['new'], enriched=outcome['enriched'])
    return summary


# --- The published base: an index of games and one entry per game -----------
#
# `GET base` (public, no account) gives the manifest: version, the sha256 of
# the index, the sources revoked since the build and the highest record id the
# base holds. The index maps each game ('system:sha256') to its entry's hash
# and its sources; the entry (`POST base/entries`) holds one part per upload.
# Only the entries of the batch's ROMs are downloaded, each verified by the
# hash that named it, and their parts join the imported banks exactly like
# fetched paths (`import_fetched`). What was imported is remembered per game in
# base-use.json, so a revoked source, a game left out of a later index or a
# rejection here withdraws exactly what came from the base.

BASE_FORMATS = (1,)
BASE_REFRESH = 30 * 60
BASE_INDEX_LIMIT = 32 * 1024 * 1024
BASE_INDEX_JSON_LIMIT = 64 * 1024 * 1024
BASE_ENTRIES_BATCH = 128
BASE_ENTRIES_LIMIT = 32 * 1024 * 1024
BASE_REJECTED_KEPT = 16
BASE_INDEX_NAME = 'base-index.json.gz'
BASE_STATE_NAME = 'base-state.json'
BASE_USE_NAME = 'base-use.json'
_SHA256 = re.compile(r'[0-9a-f]{64}')
_NETWORK_ERRORS = (ServiceError, ServiceConnectionError, OSError, ValueError)


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def _base_file(name: str) -> Path:
    # Beside the imported banks, like the cursors: removing them restarts it all.
    from .knowledge import imported_path
    return imported_path().with_name(name)


def _text(value) -> str | None:
    return value[:64] if isinstance(value, str) else None


def _base_state() -> dict:
    """The manifest facts kept from the last look at this service's base;
    {} when there are none."""
    try:
        data = json.loads(_base_file(BASE_STATE_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if (not isinstance(data, dict) or not service_url() or data.get('service') != service_url()
            or not _is_count(data.get('version')) or not isinstance(data.get('index_sha256'), str)
            or not _SHA256.fullmatch(data['index_sha256'])):
        return {}
    revoked = data.get('revoked')
    checked = data.get('checked')
    return {'service': data['service'], 'version': data['version'], 'index_sha256': data['index_sha256'],
            'revoked': sorted({value for value in revoked if _is_count(value)}) if isinstance(revoked, list) else [],
            'cursor': data['cursor'] if _is_count(data.get('cursor')) else 0,
            'games': data['games'] if _is_count(data.get('games')) else 0,
            'built_utc': _text(data.get('built_utc')), 'published_utc': _text(data.get('published_utc')),
            'checked': float(checked) if type(checked) in (int, float) else 0.0}


def _parse_index(raw: bytes, version: int) -> dict | None:
    """{'version', 'built_utc', 'games': {key: {'entry', 'sources'}}} from the
    gzipped index file, or None when it is not a format-1 index of `version`.
    A malformed game is left out; the index itself is bounded once decompressed."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            text = stream.read(BASE_INDEX_JSON_LIMIT + 1)
        if len(text) > BASE_INDEX_JSON_LIMIT:
            return None
        data = json.loads(text)
    except (OSError, EOFError, ValueError):
        return None
    if (not isinstance(data, dict) or type(data.get('format')) is not int or data['format'] not in BASE_FORMATS
            or data.get('version') != version or not isinstance(data.get('games'), dict)):
        return None
    games = {}
    for key, value in data['games'].items():
        if (isinstance(key, str) and _ROM_KEY.fullmatch(key) and isinstance(value, dict)
                and isinstance(value.get('entry'), str) and _SHA256.fullmatch(value['entry'])
                and isinstance(value.get('sources'), list)):
            games[key] = {'entry': value['entry'], 'sources': sorted({s for s in value['sources'] if _is_count(s)})}
    return {'version': version, 'built_utc': _text(data.get('built_utc')), 'games': games}


def _stored_index(state: dict) -> dict | None:
    """The index file kept beside the state, if it is still the one the state
    names (same bytes, same hash)."""
    try:
        with open(_base_file(BASE_INDEX_NAME), 'rb') as file:
            raw = file.read(BASE_INDEX_LIMIT + 1)
    except OSError:
        return None
    if len(raw) > BASE_INDEX_LIMIT or hashlib.sha256(raw).hexdigest() != state['index_sha256']:
        return None
    return _parse_index(raw, state['version'])


def _read_manifest(answer: dict) -> dict:
    """The manifest's fields, checked; ServiceError 'bad_answer' otherwise."""
    listing, revoked = answer.get('index'), answer.get('revoked')
    if (not _is_count(answer.get('version')) or not isinstance(listing, dict)
            or not isinstance(listing.get('sha256'), str) or not _SHA256.fullmatch(listing['sha256'])
            or not _is_count(listing.get('bytes')) or not 0 < listing['bytes'] <= BASE_INDEX_LIMIT
            or not isinstance(revoked, list)):
        raise ServiceError(200, 'bad_answer')
    return {'version': answer['version'], 'index_sha256': listing['sha256'], 'index_bytes': listing['bytes'],
            'revoked': sorted({value for value in revoked if _is_count(value)}),
            'cursor': answer['cursor'] if _is_count(answer.get('cursor')) else 0,
            'games': answer['games'] if _is_count(answer.get('games')) else 0,
            'built_utc': _text(answer.get('built_utc')), 'published_utc': _text(answer.get('published_utc'))}


def _refresh_base(state: dict, index: dict | None, now: float, summary: dict) -> tuple:
    """GET base: the manifest, and the index when the version changed. Returns
    the (state, index) to use: the new ones, or the stored ones when there is
    no base yet or its format is unknown (`summary['note']` says which)."""
    try:
        answer = _call('GET', 'base', timeout=15)[1]
    except ServiceError as error:
        if error.status == 404:
            summary['note'] = 'no_base'
            return state, index
        raise
    if type(answer.get('format')) is not int:
        raise ServiceError(200, 'bad_answer')
    if answer['format'] not in BASE_FORMATS:
        summary.update(note='format', format=answer['format'])
        return state, index
    manifest = _read_manifest(answer)
    if index is None or state.get('version') != manifest['version'] \
            or state.get('index_sha256') != manifest['index_sha256']:
        raw = _call('GET', f"base/index/{manifest['version']}", timeout=120, limit=manifest['index_bytes'],
                    download=True)[1]['bytes']
        if len(raw) != manifest['index_bytes'] or hashlib.sha256(raw).hexdigest() != manifest['index_sha256']:
            raise ServiceError(200, 'bad_answer')
        index = _parse_index(raw, manifest['version'])
        if index is None:
            raise ServiceError(200, 'bad_answer')
        _write_bytes(_base_file(BASE_INDEX_NAME), raw)
    state = {'service': service_url(), 'version': manifest['version'], 'index_sha256': manifest['index_sha256'],
             'revoked': manifest['revoked'], 'cursor': manifest['cursor'], 'games': manifest['games'],
             'built_utc': manifest['built_utc'], 'published_utc': manifest['published_utc'], 'checked': now}
    _write_bytes(_base_file(BASE_STATE_NAME), (json.dumps(state, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return state, index


def _blank_use() -> dict:
    return {'entry': None, 'sources': [], 'level': None, 'records': 0, 'version': None, 'imported_utc': None,
            'rejected': [], 'rejected_sources': []}


def _base_use() -> dict:
    """What the base gave each game so far: {key: {'entry' (hash of the last
    entry imported), 'sources' (its imported parts), 'level', 'records',
    'version', 'imported_utc', 'rejected' (entry hashes set aside here),
    'rejected_sources'}}. Without the imported banks nothing is imported any
    more: the rejections alone stay."""
    from .knowledge import imported_observations_path, imported_path
    try:
        data = json.loads(_base_file(BASE_USE_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    from .scan_levels import LEVELS
    banks = imported_path().is_file() or imported_observations_path().is_file()
    use = {}
    for key, value in data.items():
        if not (isinstance(key, str) and _ROM_KEY.fullmatch(key) and isinstance(value, dict)):
            continue
        rejected, sources = value.get('rejected'), value.get('sources')
        rejected_sources = value.get('rejected_sources')
        record = {'entry': value['entry'] if isinstance(value.get('entry'), str) and _SHA256.fullmatch(value['entry']) else None,
                  'sources': sorted({s for s in sources if _is_count(s)}) if isinstance(sources, list) else [],
                  'level': value['level'] if value.get('level') in LEVELS else None,
                  'records': value['records'] if _is_count(value.get('records')) else 0,
                  'version': value['version'] if _is_count(value.get('version')) else None,
                  'imported_utc': _text(value.get('imported_utc')),
                  'rejected': [s for s in rejected if isinstance(s, str) and _SHA256.fullmatch(s)][-BASE_REJECTED_KEPT:]
                  if isinstance(rejected, list) else [],
                  'rejected_sources': sorted({s for s in rejected_sources if _is_count(s)})
                  if isinstance(rejected_sources, list) else []}
        if not banks:
            record.update(entry=None, sources=[], level=None, records=0)
        use[key] = record
    return use


def _save_base_use(use: dict) -> None:
    kept = {key: value for key, value in sorted(use.items())
            if value['entry'] or value['sources'] or value['rejected']}
    _write_bytes(_base_file(BASE_USE_NAME), (json.dumps(kept, indent=1, sort_keys=True) + '\n').encode('utf-8'))


def _base_entries(shas) -> dict:
    """POST base/entries: {sha: value} of the entries the service served out
    of `shas` (the unknown ones are omitted by the service), still unverified.
    Entries the service `deferred` (its answer was full) are asked again."""
    asked, served = set(shas), {}
    ask = sorted(asked)
    for _ in range(FETCH_ROUNDS):
        answer = _call('POST', 'base/entries', payload={'entries': ask}, timeout=120,
                       limit=BASE_ENTRIES_LIMIT, compressed=True)[1]
        entries = answer.get('entries')
        if entries == []:
            entries = {}   # an empty JSON object may come back as an empty list
        if not isinstance(entries, dict):
            raise ServiceError(200, 'bad_answer')
        served.update((sha, value) for sha, value in entries.items() if sha in asked)
        deferred = answer.get('deferred') if isinstance(answer.get('deferred'), list) else []
        deferred = sorted({sha for sha in deferred if sha in asked and sha not in served})
        if not deferred or len(deferred) >= len(ask):
            break
        ask = deferred
    return served


def sync_base(rom_keys, now: float | None = None) -> dict:
    """The published base for these ROMs ('system:sha256'), needing no account:
    the manifest (at most every BASE_REFRESH seconds), the index when its
    version changed, then each game's entry as far as it differs from what was
    imported. Counts for the log: {'version', 'built_utc', 'asked', 'games'
    (received now), 'discarded' (withdrawn), 'note' (None, 'no_base' or
    'format', then 'format' names it), 'error' (a service or file error that
    stopped part of it, else None)}. The earlier base stays whenever
    something fails; nothing here raises for the network or the files."""
    now = time.time() if now is None else now
    keys = _rom_keys(rom_keys)
    summary = {'version': None, 'built_utc': None, 'asked': len(keys), 'games': 0, 'discarded': 0,
               'note': None, 'format': None, 'error': None}
    state = _base_state()
    index = _stored_index(state) if state else None
    try:
        if not (index is not None and 0 <= now - state['checked'] < BASE_REFRESH):
            state, index = _refresh_base(state, index, now, summary)
    except _NETWORK_ERRORS as caught:
        summary['error'] = caught
    if state and index is not None:
        summary.update(version=state['version'], built_utc=state['built_utc'])
        try:
            _apply_base(keys, state, index, summary)
        except _NETWORK_ERRORS as caught:
            summary['error'] = summary['error'] or caught
    return summary


def _apply_base(keys, state: dict, index: dict, summary: dict) -> None:
    """Bring the imported banks in line with the index for these ROMs."""
    from datetime import datetime, timezone
    from . import knowledge
    from .knowledge_exchange import base_entry, import_fetched, usable_part
    from .scan_levels import LEVELS
    revoked = set(state['revoked'])
    use = _base_use()
    before = json.dumps(use, sort_keys=True)
    reset, wanted = set(), {}
    for key in keys:
        listed = index['games'].get(key)
        record = use.get(key)
        entry = listed['entry'] if listed else None
        imported = set(record['sources']) if record else set()
        rejected = bool(record and entry in record['rejected'])
        sources = [source for source in listed['sources'] if source not in revoked] if listed and not rejected else []
        if imported - set(sources):
            # A part imported earlier is no longer wanted: the game's imported
            # hints go, and what remains of it is brought back part by part.
            why = ('the game left the base' if not listed else 'its entry was rejected here' if rejected
                   else 'a source was revoked' if imported & revoked else 'its entry was replaced')
            system, _, identity = key.partition(':')
            knowledge.discard_imported(system, identity, 'shared base: ' + why)
            record.update(entry=None, sources=[], level=None, records=0)
            imported = set()
            reset.add(key)
            summary['discarded'] += 1
        if not listed and record and record['entry']:
            record['entry'] = None
        if not sources or (record and record['entry'] == entry and imported == set(sources)):
            continue
        wanted[key] = entry
    current = account()
    shared = _shared_state(current) if current else {}
    if reset:
        _save_base_use(use)
        # Signed in, the per-account sync serves the game again from the start.
        for key in reset & set(shared):
            shared[key].update(cursor=0)
            shared[key].pop('level', None)
            shared[key].pop('records', None)
        if current:
            _save_shared_state(current, shared)
    failed = set()
    by_entry = {}
    for key, entry in wanted.items():
        by_entry.setdefault(entry, []).append(key)
    pending = sorted(by_entry)
    try:
        for start in range(0, len(pending), BASE_ENTRIES_BATCH):
            chunk = pending[start:start + BASE_ENTRIES_BATCH]
            try:
                served = _base_entries(chunk)
                imports = {}
                for sha in chunk:
                    for key in by_entry[sha]:
                        system, _, identity = key.partition(':')
                        found = base_entry(sha, served.get(sha), system, identity)
                        if found is None:
                            failed.add(key)   # missing or not what it claims: asked again next time
                            continue
                        parts = [part for part in found['parts'] if part['source'] not in revoked]
                        imports[key] = (sha, parts, [source for source in found['sources'] if source not in revoked])
                if imports:
                    import_fetched({key: {'records': [part['record'] for part in parts if part['record'] is not None],
                                          'observations': [row for part in parts for row in part['observations']]}
                                    for key, (sha, parts, _) in imports.items()})
            except _NETWORK_ERRORS as caught:
                summary['error'] = summary['error'] or caught
                for sha in pending[start:]:
                    failed.update(by_entry[sha])
                break
            stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
            for key, (sha, parts, sources) in imports.items():
                system, _, identity = key.partition(':')
                good = [(part, *usable_part(system, identity, part)) for part in parts]
                levels = [part['level'] for part, has_record, rows in good
                          if (has_record or rows) and part['level'] in LEVELS]
                record = use.setdefault(key, _blank_use())
                record.update(entry=sha, sources=sources,
                              level=max(levels, key=LEVELS.index) if levels else None,
                              records=sum(has_record for _, has_record, _ in good), version=state['version'],
                              imported_utc=stamp)
                summary['games'] += any(has_record or rows for _, has_record, rows in good)
    finally:
        if json.dumps(use, sort_keys=True) != before:
            _save_base_use(use)
    if current:
        # The base holds everything up to its cursor for these games: the
        # per-account sync need not serve it again. Not for a game the base
        # could not give yet, nor one just reset.
        moved = False
        for key in keys:
            if key not in reset and key not in failed and state['cursor'] > _cursor_value(shared.get(key, {}).get('cursor')):
                shared.setdefault(key, {})['cursor'] = state['cursor']
                moved = True
        if moved:
            _save_shared_state(current, shared)


def shared_paths(rom_keys) -> dict:
    """What the shared base (the published one, and with an account the
    per-account sync) gave each of these ROMs so far, for the batch:
    {key: {'level': best scan level among the paths imported, or None,
    'records': count}}."""
    from .scan_levels import LEVELS
    current = account()
    state = _shared_state(current) if current else {}
    use = _base_use()
    found = {}
    for key in rom_keys:
        fetched, published = state.get(key) or {}, use.get(key) or {}
        levels = [level for level in (fetched.get('level'), published.get('level')) if level in LEVELS]
        records = _cursor_value(fetched.get('records')) + _cursor_value(published.get('records'))
        if records or levels:
            found[key] = {'level': max(levels, key=LEVELS.index) if levels else None, 'records': records}
    return found


def forget_shared(rom_keys) -> None:
    """Shared paths set aside after they broke a conversion: their level no
    longer allows a quick check (the cursor stays, so they do not return).
    The base entry they came from is rejected too: it is not imported again
    until the index names another entry for that game."""
    keys = list(rom_keys)
    use, kept = _base_use(), False
    for key in keys:
        record = use.get(key)
        if not record or not (record['entry'] or record['sources']):
            continue
        if record['entry'] and record['entry'] not in record['rejected']:
            record['rejected'] = (record['rejected'] + [record['entry']])[-BASE_REJECTED_KEPT:]
        record['rejected_sources'] = sorted(set(record['rejected_sources']) | set(record['sources']))
        record.update(sources=[], level=None, records=0)
        kept = True
    if kept:
        _save_base_use(use)
    current = account()
    if not current:
        return
    state = _shared_state(current)
    changed = False
    for key in keys:
        entry = state.get(key)
        if entry and ('level' in entry or 'records' in entry):
            entry.pop('level', None)
            entry.pop('records', None)
            changed = True
    if changed:
        _save_shared_state(current, state)


def prepare_batch(rom_keys, enabled: bool = True, now: float | None = None) -> dict:
    """Before a batch. Without the option or the service: no request and no
    shared paths. Otherwise the published base for these ROMs (no account
    needed: 'base' is its `sync_base` summary), then, signed in, one fetch (in
    batches) of the paths found since; both join the imported banks, and
    'paths' tells each conversion what the shared base holds for its ROM. A
    failure keeps the earlier paths and never stops the batch: the base's is
    in base['error'], the fetch's in 'error'."""
    keys = _rom_keys(rom_keys)
    if not enabled or not keys or not sending_available():
        return {'paths': {}, 'summary': None, 'error': None, 'base': None}
    base = summary = error = None
    try:
        base = sync_base(keys, now)
    except _NETWORK_ERRORS as caught:
        base = {'version': None, 'built_utc': None, 'asked': len(keys), 'games': 0, 'discarded': 0,
                'note': None, 'format': None, 'error': caught}
    if account():
        try:
            summary = sync_shared(keys)
        except _NETWORK_ERRORS as caught:
            error = caught
    return {'paths': shared_paths(keys), 'summary': summary, 'error': error, 'base': base}


def send_after_batch(collect, enabled: bool = True) -> dict | None:
    """After a batch. Without the option, the service or an account: nothing,
    not even collecting. Otherwise the games whose discoveries changed are
    sent with their claims; errors reach the caller, the games stay pending."""
    if not enabled or not sending_available() or not account():
        return None
    return send(pending(collect()))


# --- Problem reports ----------------------------------------------------------
#
# A signed-in player can report a conversion that failed (or produced a wrong
# game) or write a free-text report. What leaves the computer is shown to the
# player first (`build_report` is what `send_report` posts): the game's name and
# identity, the error, the tail of the conversion's log and a few fields of
# its report. Never ROM bytes. The home folder, the user name and absolute
# paths become placeholders and e-mail addresses are removed (`scrub`).

REPORT_ERROR_LIMIT = 4 * 1024
REPORT_LOG_LIMIT = 64 * 1024
REPORT_FIELDS_LIMIT = 64 * 1024
REPORT_MESSAGE_LIMIT = 4 * 1024
REPORT_BODY_LIMIT = 256 * 1024
REPORT_PACK = 16 * 1024
REPORT_KINDS = ('conversion', 'manual')

# The fields of conversion-report.json that help to understand a failure.
# Folders, artwork, build paths and Windows metadata stay out.
REPORT_FIELDS = (
    'tool', 'version', 'created_utc', 'status', 'system', 'backend', 'engine_revision', 'sdl_revision',
    'compiler', 'compiler_signature', 'video_model', 'audio_cpu', 'input_players', 'embedded_rom', 'static_sdl',
    'native_coverage', 'native_validation', 'native_percentage', 'cartridge_device', 'hardware_accuracy_validated',
    'full_game_validated', 'latency_ms', 'physical_latency_measured', 'game_states', 'runtime_learning',
    'conversion_wall_seconds', 'executable_bytes', 'upgrade', 'shared_paths', 'bundled_paths',
    'final_checks', 'strict_checks', 'history', 'learning')
REPORT_ROM_FIELDS = ('name', 'bytes', 'crc32', 'sha256', 'system_id')
# Dropped first when the selection is too large.
REPORT_BULKY = ('history', 'strict_checks', 'learning', 'final_checks', 'native_validation', 'native_coverage')

_EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+')
_DRIVE_PATH = re.compile(r'(?<![\w])[A-Za-z]:[\\/]+[^\s"\'<>|*?:]*')
_UNC_PATH = re.compile(r'(?<![\w\\])\\\\+[^\s\\/"\'<>|*?:]+[\\/]+[^\s"\'<>|*?:]*')
_POSIX_PATH = re.compile(r'(?<![\w<>.:/\\-])/(?:home|Users|root|mnt|media|run|tmp|var|opt|srv|usr|private|Volumes|'
                         r'Library|data|storage|sdcard)(?:/[^\s"\'<>|*?:]*)?')
_PATH_END = '.,;)]}'


def _root_pattern(path):
    """A pattern for a folder in any spelling: either slash, repeated
    backslashes (as a repr shows them), any case."""
    text = str(path).strip()
    parts = [part for part in re.split(r'[\\/]+', text) if part]
    if not parts:
        return None
    lead = r'[\\/]{1,4}' if text[:1] in '\\/' else ''
    return re.compile(lead + r'[\\/]+'.join(re.escape(part) for part in parts) + r'(?![\w-])', re.IGNORECASE)


def _user_names() -> set:
    import getpass
    names = {os.environ.get('USERNAME', ''), os.environ.get('USER', ''), Path.home().name}
    try:
        names.add(getpass.getuser())
    except Exception:   # no user database (some containers)
        pass
    return {name for name in names if len(name) >= 3}


def _generic_path(match) -> str:
    text = match.group(0)
    tail = ''
    while text and text[-1] in _PATH_END:
        text, tail = text[:-1], text[-1] + tail
    last = re.split(r'[\\/]+', text.rstrip('\\/'))[-1]
    return '<path>' + ('/' + last if '.' in last and not last.startswith('.') else '') + tail


class Scrubber:
    """Replaces what identifies the player. `roots` are (placeholder, folder)
    pairs such as ('<games>', games folder) or ('<rom>', a ROM folder); the
    home folder, the temporary folder and this installation are always known."""

    def __init__(self, roots=()):
        from .paths import ROOT
        known = [(name, folder) for name, folder in roots if folder]
        known += [('<app>', ROOT), ('<temp>', tempfile.gettempdir()), ('<home>', Path.home())]
        # The longest folder first: a games folder inside the home folder is <games>.
        known.sort(key=lambda pair: -len(str(pair[1])))
        patterns = [(name, _root_pattern(folder)) for name, folder in known]
        self.roots = [(name, pattern) for name, pattern in patterns if pattern is not None]
        names = sorted(_user_names(), key=len, reverse=True)
        self.user = (re.compile(r'(?<![\w])(?:' + '|'.join(map(re.escape, names)) + r')(?![\w])', re.IGNORECASE)
                     if names else None)

    def text(self, value) -> str:
        if not isinstance(value, str):
            return ''
        value = _EMAIL.sub('<email>', value)
        for placeholder, pattern in self.roots:
            value = pattern.sub(lambda match, placeholder=placeholder: placeholder, value)
        for pattern in (_DRIVE_PATH, _UNC_PATH, _POSIX_PATH):
            value = pattern.sub(_generic_path, value)
        return self.user.sub('<user>', value) if self.user else value

    def value(self, value):
        """The same, through nested lists and dictionaries (JSON values)."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            return {self.text(str(key)): self.value(item) for key, item in value.items()}
        return value


def scrub(value, roots=()):
    """`value` (text or JSON-like data) without the home folder, user name,
    absolute paths or e-mail addresses."""
    return Scrubber(roots).value(value)


def _head(text: str, limit: int) -> str:
    data = text.encode('utf-8')
    return text if len(data) <= limit else data[:limit].decode('utf-8', 'ignore')


def _tail(text: str, limit: int) -> str:
    """The end of a log, from a whole line, within `limit` bytes."""
    data = text.encode('utf-8')
    if len(data) <= limit:
        return text
    cut = data[-limit:].decode('utf-8', 'ignore')
    newline = cut.find('\n')
    return cut[newline + 1:] if 0 <= newline < len(cut) - 1 else cut


def _json_size(value) -> int:
    """Bytes of `value` as it travels (non-ASCII escaped, the larger form)."""
    return len(json.dumps(value, separators=(',', ':')).encode('utf-8'))


def report_fields(report, roots=()):
    """The selected fields of a conversion report, scrubbed and within
    REPORT_FIELDS_LIMIT (the bulkiest are dropped first); None without one."""
    if not isinstance(report, dict):
        return None
    chosen = {key: report[key] for key in REPORT_FIELDS if key in report}
    chosen.update({key: value for key, value in report.items() if key.startswith('reference_')})
    if isinstance(report.get('rom'), dict):
        chosen['rom'] = {key: report['rom'][key] for key in REPORT_ROM_FIELDS if key in report['rom']}
    chosen = Scrubber(roots).value(chosen)
    for key in REPORT_BULKY:
        if _json_size(chosen) <= REPORT_FIELDS_LIMIT:
            break
        chosen.pop(key, None)
    while chosen and _json_size(chosen) > REPORT_FIELDS_LIMIT:
        chosen.pop(max(chosen, key=lambda key: _json_size(chosen[key])))
    return chosen or None


def report_platform() -> str:
    from .platforms import target_id
    try:
        target = target_id()
    except RuntimeError:
        return sys.platform
    return target.replace('windows-x86_64', 'windows-x64')


def build_report(kind: str, *, game: dict | None = None, error: str | None = None, log: str | None = None,
                 report: dict | None = None, message: str = '', language: str = 'en', roots=()) -> dict:
    """The exact body of `POST reports`, private data already removed.
    `game` is {'system', 'identity' (64 hex), 'title'}; without a valid
    identity it is left out and the title goes into the error."""
    if kind not in REPORT_KINDS:
        raise ValueError(f'Unknown report kind: {kind!r}')
    cleaner = Scrubber(roots)
    message = _head(cleaner.text((message or '').strip()), REPORT_MESSAGE_LIMIT)
    if kind == 'manual' and not message:
        raise ValueError('A free-text report needs a message.')
    entry = None
    if isinstance(game, dict) and game.get('system') and re.fullmatch(r'[0-9a-f]{64}', str(game.get('identity') or '')):
        entry = {'system': str(game['system']), 'identity': game['identity'],
                 'title': cleaner.text(str(game.get('title') or ''))[:200]}
    elif isinstance(game, dict) and game.get('title') and error:
        error = f"{game['title']}: {error}"
    text = _head(cleaner.text(error), REPORT_ERROR_LIMIT) if error else None
    tail = _tail(cleaner.text(log), REPORT_LOG_LIMIT) if log else None
    body = {'kind': kind, 'converter': __version__, 'platform': report_platform(), 'language': language,
            'game': entry, 'error': text or None, 'log': tail or None,
            'report': report_fields(report, roots), 'message': message}
    # The service refuses (it never truncates) a body above REPORT_BODY_LIMIT
    # once decompressed: escaped non-ASCII text can grow, so the log's start
    # (then the report) gives way until the body fits.
    while _json_size(body) > REPORT_BODY_LIMIT:
        if body['log']:
            body['log'] = _tail(body['log'], len(body['log'].encode('utf-8')) * 3 // 4) or None
        elif body['report']:
            body['report'] = None
        else:
            break
    return body


def send_report(kind: str, *, game: dict | None = None, error: str | None = None, log: str | None = None,
                report: dict | None = None, message: str = '', language: str = 'en', roots=()) -> int:
    """Send a problem report with the signed-in account; returns its id.
    Raises ServiceError (401 without an account; 413 too_large, 429
    rate_limited, 400 invalid_report from the service) or
    ServiceConnectionError."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    body = build_report(kind, game=game, error=error, log=log, report=report, message=message,
                        language=language, roots=roots)
    try:
        answer = _call('POST', 'reports', payload=body, token=current['token'], timeout=30, pack=REPORT_PACK)[1]
    except ServiceError as caught:
        if caught.status == 401:
            _save_account(None)   # revoked or deleted elsewhere: sign in again
        raise
    identifier = answer.get('id')
    if type(identifier) is not int:
        raise ServiceError(200, 'bad_answer')
    return identifier
