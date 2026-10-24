"""The shared Retro-Recomp base: sign-in by e-mailed code and discovery uploads.

Only what `knowledge_exchange.write_knowledge` writes is sent: the same
ROM-free `.rrknowledge` file as a manual export (numbers and short titles, no
ROM byte, path, image or code). The account is an e-mail address proven by a
one-time code; the converter keeps a revocable token in `datas/account.json`,
which is never exported. A game is marked as shared only once the server has
accepted it, so a failed or offline upload is simply retried next time. The
server queues uploads for the maintainer, who revalidates them and only adds
discoveries to a future bundled snapshot after his own qualified conversions.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import tempfile
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


class ServiceConnectionError(Exception):
    """The service could not be reached through the current network."""


class ServiceError(Exception):
    """The service answered with an error; `reason` is its stable code."""

    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


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
          token: str | None = None, timeout: int = 20) -> tuple[int, dict]:
    base = service_url()
    if not base:
        raise ServiceError(0, 'unavailable')
    headers = {'User-Agent': f'RetroRecomp/{__version__}', 'Accept': 'application/json'}
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
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
            raw = response.read(ANSWER_LIMIT + 1)
            status = response.status if hasattr(response, 'status') else response.code
    except (OSError, http.client.IncompleteRead) as error:
        raise ServiceConnectionError() from error
    try:
        answer = json.loads(raw) if len(raw) <= ANSWER_LIMIT else None
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise ServiceError(status, 'bad_answer')
    if status >= 400:
        reason = answer.get('error')
        raise ServiceError(status, reason if isinstance(reason, str) else 'error')
    return status, answer


def status() -> dict:
    return _call('GET', 'status')[1]


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
    """The player's own portrait as the server re-encoded it (WebP, 256 px),
    pending or approved; None without an account or a portrait."""
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
# at most every PLAYER_REFRESH seconds (or after a sign-in); the portrait is
# downloaded again only when its public file name changes on the site.
PLAYER_NAME = 'account-player.json'
AVATAR_NAME = 'account-avatar.webp'
PLAYER_REFRESH = 30 * 60


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
    return {'account': current, 'profile': data.get('profile') or {}, 'board': data.get('board') or {},
            'avatar': avatar_bytes, 'fetched': data.get('fetched', 0)}


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
    return {'account': current, 'profile': details, 'board': {'you': you}, 'avatar': picture, 'fetched': now}


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


def sign_in(email: str, code: str, label: str = '') -> dict:
    """Trade the e-mailed code for this converter's token, remembered locally."""
    answer = _call('POST', 'auth/token', payload={'email': email, 'code': code, 'label': label[:64]})[1]
    token, details = answer.get('token'), answer.get('account')
    if not isinstance(token, str) or not token.startswith('rr1_') or not isinstance(details, dict):
        raise ServiceError(200, 'bad_answer')
    data = {'service': service_url(), 'token': token, 'email': str(details.get('email') or email),
            'pseudonym': details.get('pseudonym') if isinstance(details.get('pseudonym'), str) else None}
    _save_account(data)
    return data


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
    they were last sent with an account."""
    from .knowledge_exchange import pending_since_shared
    return _restrict(collected, set(pending_since_shared('account', collected)))


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
    channel, so an interrupted send resumes with the games still pending."""
    current = account()
    if not current:
        raise ServiceError(401, 'unauthorized')
    if not collected['games']:
        return {'games': 0, 'discoveries': 0}
    parts = _parts(collected)
    if len(parts) == 1:
        return _send_one(collected, current)
    total = {'games': 0, 'discoveries': 0, 'bytes': 0, 'files': 0, 'duplicate': True}
    for keys in parts:
        result = _send_one(_restrict(collected, keys), current)
        total['games'] += result['games']
        total['discoveries'] += result['discoveries']
        total['bytes'] += result['bytes']
        total['files'] += 1
        total['duplicate'] = total['duplicate'] and result['duplicate']
        total['id'] = result.get('id')
    return total


def _send_one(collected: dict, current: dict) -> dict:
    from .knowledge_exchange import mark_shared, write_knowledge
    from .paths import data_directory
    folder = data_directory() / 'knowledge'
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='upload-', suffix='.rrknowledge', dir=folder)
    os.close(fd)
    try:
        write_knowledge(collected, Path(name), channel=None)
        body = Path(name).read_bytes()
    finally:
        os.unlink(name)
    if len(body) > UPLOAD_LIMIT:
        raise ServiceError(413, 'too_large')
    try:
        code, answer = _call('POST', 'contributions', body=body, token=current['token'], timeout=60)
    except ServiceError as error:
        if error.status == 401:
            _save_account(None)   # revoked or deleted elsewhere: sign in again
        raise
    mark_shared('account', collected)
    # The scan level of each qualified game rides beside the file (which
    # keeps its format); losing it only costs the scan bonus.
    levels = {f'{system}:{identity}': level for system, values in collected.get('levels', {}).items()
              for identity, level in values.items()}
    if levels and isinstance(answer.get('id'), int) and code == 201:
        try:
            _call('POST', f"contributions/{answer['id']}/levels", payload={'levels': levels}, token=current['token'])
        except (ServiceError, ServiceConnectionError):
            pass
    return {'games': collected['games'], 'discoveries': collected['discoveries'], 'bytes': len(body),
            'id': answer.get('id'), 'duplicate': bool(answer.get('duplicate')) or code == 200}
