"""Where does each pinned upstream stand? (docs/UPSTREAMS.md)

    python -B tools/check_upstreams.py            # online: commits ahead, compare URL, latest commit date
    python -B tools/check_upstreams.py --list     # offline: only the pins the code holds
    python -B tools/check_upstreams.py --json     # the online rows as JSON
    python -B tools/check_upstreams.py --only snesrecomp --only SDL

The rows come from retrorecomp/upstreams.py (one declaration per machine plus the shared ones) and each pin is
read from the code itself, so a new machine appears here without editing this file. A network failure is
reported on its own row and never stops the others. The tool needs no ROM and no secret (an optional
GITHUB_TOKEN or GH_TOKEN only raises the public API's rate limit), reads `.deps` only through
`git ls-tree` and never writes into it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import upstreams  # noqa: E402

API = 'https://api.github.com/'
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
TIMEOUT = 30


class ApiError(RuntimeError):
    pass


def api(path: str, params: dict | None = None):
    """GET one GitHub API path as JSON: through `gh` when it is installed and signed in, else urllib."""
    query = '?' + urllib.parse.urlencode(params) if params else ''
    failure = ''
    gh = shutil.which('gh')
    if gh:
        try:
            done = subprocess.run([gh, 'api', path + query], capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=TIMEOUT, creationflags=NO_WINDOW)
            if done.returncode == 0:
                return json.loads(done.stdout)
            failure = (done.stderr or done.stdout).strip().splitlines()[-1:] or ['gh failed']
            failure = failure[0]
            if 'HTTP 404' in failure:
                raise ApiError(failure)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            failure = str(error)
    request = urllib.request.Request(API + path + query, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'retro-recomp-check-upstreams'})
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as stream:
            return json.loads(stream.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise ApiError(f'HTTP {error.code} {error.reason}' + (f' (gh: {failure})' if failure else '')) from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ApiError(f'{error}' + (f' (gh: {failure})' if failure else '')) from error


def pins(root: Path = ROOT) -> list[dict]:
    """The offline rows: one per upstream, with the pin read from the code and the places that disagree."""
    rows = []
    for item in upstreams.all_upstreams():
        pin = upstreams.pin_of(item, root)
        mismatch = []
        for other in item.also:
            value = upstreams.read_pin(other, root)
            if value != pin:
                mismatch.append(f'{other.where} holds {value!r}')
        rows.append({'key': item.key, 'repo': item.repo, 'consoles': list(upstreams.consoles_of(item)),
                     'pin': pin, 'pin_short': (pin or '')[:7] if not item.is_version else pin,
                     'where': item.pin.where, 'kind': 'version' if item.is_version else 'commit',
                     'branch': item.branch, 'mismatch': mismatch})
    return rows


def _row_commit(item, row: dict) -> None:
    pin, repo, branch = row['pin'], item.repo, item.branch
    row['compare_url'] = f'https://github.com/{repo}/compare/{pin}...{branch}'
    latest = api(f'repos/{repo}/commits/{urllib.parse.quote(branch)}')
    row['latest_sha'] = latest['sha']
    row['latest_date'] = latest['commit']['committer']['date'][:10]
    compare = api(f'repos/{repo}/compare/{pin}...{urllib.parse.quote(branch)}', {'per_page': 1})
    row['ahead'] = compare['ahead_by']
    row['behind'] = compare['behind_by']
    row['relation'] = compare['status']
    row['ahead_all'] = compare['ahead_by']
    row['scope'] = 'all commits'
    if item.watch and row['ahead']:
        since = api(f'repos/{repo}/commits/{pin}')['commit']['committer']['date']
        touching = set()
        for path in item.watch:
            for entry in api(f'repos/{repo}/commits', {'sha': branch, 'path': path, 'since': since, 'per_page': 100}):
                touching.add(entry['sha'])
        touching.discard(pin)
        row['ahead'] = len(touching)
    if item.watch:
        row['scope'] = 'watched files'


def _row_version(item, row: dict) -> None:
    release = api(f'repos/{item.repo}/releases/latest')
    tag = release['tag_name']
    pinned = upstreams.release_tag(item, row['pin'])
    row['latest_sha'] = tag
    row['latest_date'] = (release.get('published_at') or '')[:10]
    row['relation'] = 'identical' if tag == pinned else 'newer release'
    row['ahead'] = None
    row['scope'] = 'latest release tag'
    row['compare_url'] = f'https://github.com/{item.repo}/compare/{pinned}...{tag}'


def _submodule_pin(item, row: dict) -> None:
    """A submodule pin that .deps could not give: ask the parent's pinned tree on GitHub."""
    parent_pin = upstreams.pin_of(item.parent)
    if not parent_pin:
        raise ApiError('the parent pin cannot be read')
    entry = api(f'repos/{item.parent.repo}/contents/{item.pin.path}', {'ref': parent_pin})
    row['pin'] = entry.get('sha')
    row['pin_short'] = (row['pin'] or '')[:7]


def check(item, row: dict) -> dict:
    """The online part of one row. Every failure lands in row['error']."""
    row = dict(row, ahead=None, latest_date=None, latest_sha=None, compare_url=None, relation=None, scope='', error=None)
    try:
        if not row['pin'] and item.pin.kind == 'submodule':
            _submodule_pin(item, row)
        if not row['pin']:
            raise ApiError(f'pin not readable from {row["where"]}')
        (_row_version if item.is_version else _row_commit)(item, row)
    except (ApiError, KeyError, TypeError, ValueError) as error:
        row['error'] = str(error) or error.__class__.__name__
    return row


def run_online(selected, root: Path = ROOT, jobs: int = 4) -> list[dict]:
    base = {row['key']: row for row in pins(root)}
    items = [item for item in upstreams.all_upstreams() if not selected or item.key in selected]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(lambda item: check(item, base[item.key]), items))


def print_list(rows: list[dict]) -> None:
    width = max(len(row['key']) for row in rows)
    for row in rows:
        pin = row['pin'] or ('see docs/UPSTREAMS.md' if row['where'].startswith('submodule') else 'NOT READABLE')
        print(f"{row['key']:<{width}}  {pin:<40}  {row['where']}  [{','.join(row['consoles'])}]")
        for text in row['mismatch']:
            print(f"{'':<{width}}  MISMATCH: {text}")


def print_table(rows: list[dict]) -> None:
    width = max(len(row['key']) for row in rows)
    print(f"{'upstream':<{width}}  {'pin':<9}  {'ahead':<7}  {'latest':<10}  note")
    for row in rows:
        pin = row['pin_short'] or '?'
        if row['error']:
            print(f"{row['key']:<{width}}  {pin:<9}  {'-':<7}  {'-':<10}  ERROR: {row['error']}")
            continue
        ahead = '-' if row['ahead'] is None else str(row['ahead'])
        note = row['relation'] + ('' if row['kind'] == 'version' else f" on {row['branch']}")
        if row['kind'] == 'version':
            note += f" (latest {row['latest_sha']})"
        elif row['scope'] != 'all commits':
            note += f" ({row['ahead_all']} in all; the figure counts only the {row['scope']})"
        print(f"{row['key']:<{width}}  {pin:<9}  {ahead:<7}  {row['latest_date'] or '-':<10}  {note}")
        if row['ahead'] or (row['kind'] == 'version' and row['relation'] != 'identical'):
            print(f"{'':<{width}}  {row['compare_url']}")
    failed = sum(1 for row in rows if row['error'])
    if failed:
        print(f'\n{failed} row(s) could not be checked (network or API error); the others are valid.')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--list', action='store_true', help='offline: print the pins the code holds and stop')
    parser.add_argument('--json', action='store_true', help='print the rows as JSON')
    parser.add_argument('--only', action='append', default=[], metavar='KEY', help='check only this upstream (repeatable)')
    parser.add_argument('--jobs', type=int, default=4, help='parallel API requests (default 4)')
    parser.add_argument('--strict', action='store_true', help='exit 1 when a pin is unreadable or a row failed')
    args = parser.parse_args(argv)
    known = {item.key for item in upstreams.all_upstreams()}
    unknown = sorted(set(args.only) - known)
    if unknown:
        parser.error('unknown upstream(s): ' + ', '.join(unknown) + '; known: ' + ', '.join(sorted(known)))
    if args.list:
        rows = [row for row in pins() if not args.only or row['key'] in args.only]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print_list(rows)
        bad = any(row['mismatch'] or (not row['pin'] and not row['where'].startswith('submodule')) for row in rows)
        return 1 if bad and args.strict else 0
    rows = run_online(set(args.only), jobs=max(1, args.jobs))
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)
    return 1 if args.strict and any(row['error'] or row['mismatch'] for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
