"""Reviewed public cover links, without artwork, ROM bytes or private paths."""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import re
import urllib.parse

from .paths import ASSETS

RESOURCE = 'assets/cover-references.json'
MAX_BYTES = 1024 * 1024
SYSTEMS = frozenset(('sms', 'gg', 'gb', 'nes', 'md', 'snes'))
FIELDS = frozenset(('id', 'system_id', 'rom_sha256', 'rom_names', 'style',
                    'image_urls', 'source_page'))


def public_url(value: str) -> bool:
    """References must be public, credential-free HTTPS links, not local files."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)
                or '.' not in host or host.endswith('.local') or host == 'localhost'):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def validate_payload(value: dict) -> dict:
    """An allowlist schema prevents embedded images or private histories."""
    if (not isinstance(value, dict) or set(value) != {'format', 'entries'}
            or type(value['format']) is not int or value['format'] != 1
            or not isinstance(value['entries'], list) or len(value['entries']) > 5000):
        raise ValueError('Invalid public cover-reference format.')
    identifiers = set()
    for record in value['entries']:
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError('Cover references may contain declared metadata and links only.')
        identity = record['id']
        if (not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', identity)
                or identity in identifiers):
            raise ValueError('Invalid or duplicate cover-reference ID.')
        identifiers.add(identity)
        if (not isinstance(record['system_id'], str) or record['system_id'] not in SYSTEMS
                or record['style'] not in ('front', 'box3d')):
            raise ValueError('Invalid cover console or style.')
        hashes, names, urls = record['rom_sha256'], record['rom_names'], record['image_urls']
        if (not all(isinstance(items, list) for items in (hashes, names, urls))
                or not (hashes or names) or not 1 <= len(urls) <= 4
                or len(hashes) > 100 or len(names) > 100):
            raise ValueError('Invalid cover-reference selectors.')
        if any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h) for h in hashes):
            raise ValueError('Invalid cover ROM identity.')
        if any(not isinstance(n, str) or not n.strip() or len(n) > 240
               or any(c in n for c in '/\\:\0\r\n') for n in names):
            raise ValueError('Cover names must not contain filesystem paths.')
        if any(not public_url(url) for url in (*urls, record['source_page'])):
            raise ValueError('Cover references require public HTTPS URLs without credentials.')
    return value


def load(path: Path | None = None) -> dict:
    try:
        resource = path or ASSETS / RESOURCE
        with resource.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Cover references exceed their size limit.')
        return validate_payload(json.loads(data))
    except (OSError, ValueError, TypeError, KeyError):
        return {'format': 1, 'entries': []}


def find(system_id: str, rom_sha256: str | None, rom_name: str, *, prefer3d=False) -> dict | None:
    from .artwork import normalized
    records = [r for r in load()['entries'] if r['system_id'] == system_id
               and r['style'] == ('box3d' if prefer3d else 'front')]
    matches = [r for r in records if rom_sha256 and rom_sha256 in r['rom_sha256']]
    if not matches:
        matches = [r for r in records if any(normalized(n) == normalized(rom_name)
                                            for n in r['rom_names'])]
    if len(matches) != 1:
        return None  # Do not resolve ambiguous editions or similarly named sequels.
    record = dict(matches[0])
    record['revision'] = hashlib.sha256(json.dumps(record, sort_keys=True,
                                                  separators=(',', ':')).encode()).hexdigest()
    return record
