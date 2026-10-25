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
are checked again by every conversion.
"""
from __future__ import annotations

import gzip
import http.client
import io
import json
import os
from pathlib import Path
import re
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
          token: str | None = None, timeout: int = 20, limit: int = ANSWER_LIMIT,
          compressed: bool = False, pack: bool = False) -> tuple[int, dict]:
    """One API request. `compressed` asks for a gzipped answer; `limit`
    bounds the answer read and, once decompressed, the JSON parsed. With
    `pack`, a JSON body above GZIP_BODY leaves gzipped."""
    base = service_url()
    if not base:
        raise ServiceError(0, 'unavailable')
    headers = {'User-Agent': f'RetroRecomp/{__version__}', 'Accept': 'application/json'}
    if compressed:
        headers['Accept-Encoding'] = 'gzip'
    if payload is not None:
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        if pack and len(body) > GZIP_BODY:
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
        raise
    mark_shared('account', collected)
    # The scan level of each qualified game rides beside the file (which
    # keeps its format), in the claims; losing it only costs the scan bonus.
    levels = {f'{system}:{identity}': level for system, values in collected.get('levels', {}).items()
              for identity, level in values.items()}
    contribution, claimed, refused = answer.get('id'), None, None
    games = claim_games(paths, levels)
    # 201: a new file; 200: this account's earlier copy, whose claims are idempotent.
    if isinstance(contribution, int) and code in (200, 201) and games:
        claimed, refused = _deliver_claims(contribution, games, levels if code == 201 else {}, current)
    return {'games': collected['games'], 'discoveries': collected['discoveries'], 'bytes': len(body),
            'id': contribution, 'duplicate': bool(answer.get('duplicate')) or code == 200, 'claims': claimed,
            'claims_refused': refused}


# --- Claims: the paths each accepted file brings, for immediate points -----

def claim_games(paths: dict, levels: dict) -> list:
    """The claims body's games, from `discovery_paths` of the uploaded file.
    A game without a qualified conversion (raw observations only) counts at
    the standard level, as before scan levels were sent."""
    return [{'system': system, 'identity': identity, 'known': bool(value['known']),
             'level': levels.get(f'{system}:{identity}', 'standard'),
             'hints': list(value['hints']), 'observations': list(value['observations'])}
            for (system, identity), value in sorted(paths.items())
            if value['hints'] or value['observations']]


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
    total = {'games': 0, 'paths': 0, 'new': 0}
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
    return {name: sum(answer.get(name, 0) for answer in answered) for name in ('games', 'paths', 'new')}


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


def shared_paths(rom_keys) -> dict:
    """What the shared base gave each of these ROMs so far, for the batch:
    {key: {'level': best scan level or None, 'records': count}}."""
    current = account()
    if not current:
        return {}
    state = _shared_state(current)
    found = {}
    for key in rom_keys:
        entry = state.get(key) or {}
        if entry.get('records') or entry.get('level'):
            found[key] = {'level': entry.get('level'), 'records': _cursor_value(entry.get('records'))}
    return found


def forget_shared(rom_keys) -> None:
    """Shared paths set aside after they broke a conversion: their level no
    longer allows a quick check (the cursor stays, so they do not return)."""
    current = account()
    if not current:
        return
    state = _shared_state(current)
    changed = False
    for key in rom_keys:
        entry = state.get(key)
        if entry and ('level' in entry or 'records' in entry):
            entry.pop('level', None)
            entry.pop('records', None)
            changed = True
    if changed:
        _save_shared_state(current, state)


def prepare_batch(rom_keys, enabled: bool = True) -> dict:
    """Before a batch. Without the option, the service or an account: no
    request and no shared paths. Otherwise one fetch (in batches) whose paths
    join the imported banks; 'paths' then tells each conversion what the
    shared base holds for its ROM. A failed fetch keeps the earlier paths."""
    keys = _rom_keys(rom_keys)
    if not enabled or not keys or not sending_available() or not account():
        return {'paths': {}, 'summary': None, 'error': None}
    summary = error = None
    try:
        summary = sync_shared(keys)
    except (ServiceError, ServiceConnectionError, OSError, ValueError) as caught:
        error = caught
    return {'paths': shared_paths(keys), 'summary': summary, 'error': error}


def send_after_batch(collect, enabled: bool = True) -> dict | None:
    """After a batch. Without the option, the service or an account: nothing,
    not even collecting. Otherwise the games whose discoveries changed are
    sent with their claims; errors reach the caller, the games stay pending."""
    if not enabled or not sending_available() or not account():
        return None
    return send(pending(collect()))
