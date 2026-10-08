"""Private cover-service settings, protected with the current Windows account.

Loading defaults creates nothing. API secrets are never part of general
preferences, generated games, publication resources or downloaded metadata.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
from pathlib import Path
import tempfile
import uuid

from .paths import data_directory

FIELDS = {
    'screenscraper': ('devid', 'devpassword', 'ssid', 'sspassword'),
    'thegamesdb': ('apikey',),
    'igdb': ('client_id', 'client_secret'),
}
CONFIG_NAME = 'cover-sources.json'


def defaults() -> dict:
    return {'box_3d': False, 'accounts': {name: dict.fromkeys(fields, '')
            for name, fields in FIELDS.items()}}


def _accounts(value: dict) -> dict:
    accounts = defaults()['accounts']
    for provider, fields in accounts.items():
        source = value.get(provider, {})
        if not isinstance(source, dict):
            continue
        for key in fields:
            text = source.get(key, '')
            if isinstance(text, str) and len(text) <= 4096:
                fields[key] = text.strip()
    return accounts


def _protect(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise ValueError('Saving API credentials requires Windows account protection.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    def blob(value):
        buffer = ctypes.create_string_buffer(value)
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer

    source, source_buffer = blob(data)
    entropy, entropy_buffer = blob(b'RetroRecomp.cover-sources.v1')
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    protect = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    protect.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
    protect.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not protect(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(output)):
        raise ValueError('Windows could not protect or unlock the cover-service credentials.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load_settings(directory: Path | None = None) -> dict:
    result = defaults()
    try:
        record = json.loads(((directory or data_directory()) / CONFIG_NAME).read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            return result
        result['box_3d'] = record.get('box_3d', False) is True
        if isinstance(record.get('revision'), str):
            result['revision'] = record['revision']
        if record.get('protected_accounts'):
            secret = _protect(base64.b64decode(record['protected_accounts'], validate=True), decrypt=True)
            result['accounts'] = _accounts(json.loads(secret))
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, AttributeError):
        # No raw parser or transport exception: it could contain a secret.
        result['credential_error'] = True
    return result


def save_settings(value: dict, directory: Path | None = None) -> None:
    accounts = _accounts(value.get('accounts', {}))
    record = {'version': 1, 'box_3d': bool(value.get('box_3d', False)), 'revision': uuid.uuid4().hex}
    if any(text for fields in accounts.values() for text in fields.values()):
        raw = json.dumps(accounts, ensure_ascii=False).encode('utf-8')
        record['protected_accounts'] = base64.b64encode(_protect(raw)).decode('ascii')
    directory = directory or data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='cover-sources.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
        os.replace(temporary, directory / CONFIG_NAME)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configured(provider: str, account: dict) -> bool:
    required = {'screenscraper': ('devid', 'devpassword'),
                'thegamesdb': ('apikey',), 'igdb': ('client_id', 'client_secret')}
    return all(account.get(key) for key in required.get(provider, ())) and provider in required
