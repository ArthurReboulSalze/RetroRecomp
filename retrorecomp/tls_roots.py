"""Find the system's CA bundle for the frozen Linux converter.

The Linux release is built on Debian, so the OpenSSL it carries looks for
certificates only at Debian's compiled-in path (/usr/lib/ssl/cert.pem). On
Fedora, Bazzite, Arch, openSUSE or Alpine that path does not exist, every HTTPS
request fails certificate verification, and the player sees only "no
connection". This module points OpenSSL at the bundle the distribution really
keeps, once, before the first request. Windows and macOS are never touched.
Nothing is bundled: the distribution's own store (with the administrator's
additions) stays the single source of trust.
"""
from __future__ import annotations

import os
from pathlib import Path
import ssl
import sys

# One concatenated PEM file per distribution family, most common first.
BUNDLE_PATHS = (
    '/etc/ssl/certs/ca-certificates.crt',      # Debian, Ubuntu, Arch (symlink), Alpine
    '/etc/pki/tls/certs/ca-bundle.crt',        # Fedora, RHEL, Bazzite and other Fedora Atomic
    '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',   # the same bundle, extracted path
    '/etc/ssl/ca-bundle.pem',                  # openSUSE
    '/var/lib/ca-certificates/ca-bundle.pem',  # openSUSE (older)
    '/etc/ssl/cert.pem',                       # Alpine, some BSD-like layouts
    '/etc/pki/tls/cacert.pem',                 # old RHEL
    '/usr/share/ca-certificates/ca-bundle.crt',
    '/usr/share/ssl/certs/ca-bundle.crt',
)

_state: dict = {'done': False, 'path': None, 'warned': False}


def _usable(path) -> bool:
    try:
        return bool(path) and Path(path).is_file() and Path(path).stat().st_size > 0
    except OSError:
        return False


def _default_store_works() -> bool:
    """True when OpenSSL's own compiled-in locations already hold certificates."""
    paths = ssl.get_default_verify_paths()
    if _usable(paths.cafile):
        return True
    try:
        return bool(paths.capath) and any(Path(paths.capath).iterdir())
    except OSError:
        return False


def find_bundle(paths=BUNDLE_PATHS) -> str | None:
    for candidate in paths:
        if _usable(candidate):
            return candidate
    return None


def ensure(platform: str | None = None, environ=None, paths=BUNDLE_PATHS) -> str | None:
    """Set SSL_CERT_FILE to a system bundle when OpenSSL cannot find its own.

    Idempotent; returns the bundle used, or None when nothing was needed or
    nothing was found. A SSL_CERT_FILE or SSL_CERT_DIR the player set, or a
    default store that works, is never overridden."""
    environ = os.environ if environ is None else environ
    if _state['done'] and platform is None and environ is os.environ:
        return _state['path']
    if (platform or sys.platform) != 'linux':
        return None
    if environ is os.environ:
        _state['done'] = True
    if _usable(environ.get('SSL_CERT_FILE')) or environ.get('SSL_CERT_DIR'):
        return None
    if environ is os.environ and _default_store_works():
        return None
    found = find_bundle(paths)
    if found:
        environ['SSL_CERT_FILE'] = found
        if environ is os.environ:
            _state['path'] = found
    return found


def is_verification_failure(error: BaseException | None) -> bool:
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            return True
        reason = getattr(error, 'reason', None)
        error = reason if isinstance(reason, BaseException) else (error.__cause__ or error.__context__)
    return False


def note_failure(error: BaseException | None, write=None) -> bool:
    """Say once on stderr that a request failed on certificate verification
    (the window only shows 'no connection'). Returns True when it did."""
    if _state['warned'] or not is_verification_failure(error):
        return False
    _state['warned'] = True
    write = write or (lambda text: print(text, file=sys.stderr))
    if sys.platform == 'linux' and _state['path'] is None and find_bundle() is None:
        write('Retro-Recomp: HTTPS certificate verification failed and no system CA bundle was found. '
              'Install your distribution\'s ca-certificates package, or set SSL_CERT_FILE to a PEM bundle.')
    else:
        write('Retro-Recomp: HTTPS certificate verification failed (' + str(_state['path'] or 'default store')
              + '). The system clock, a proxy or an outdated CA bundle can cause it; '
                'SSL_CERT_FILE can name another PEM bundle.')
    return True
