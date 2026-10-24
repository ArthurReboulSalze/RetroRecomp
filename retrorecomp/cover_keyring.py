"""Linux Secret Service storage. No file-based or unencrypted fallback."""
from contextlib import contextmanager
import re


class KeyringError(ValueError):
    """Safe to display: never contains service responses or account values."""


def attributes(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{32}', identity):
        raise KeyringError('Invalid cover-account reference.')
    return {'application': 'RetroRecomp', 'cover-account-id': identity}


@contextmanager
def collection(*, unlock=False):
    connection = None
    try:
        import secretstorage
        connection = secretstorage.dbus_init()
        # Do not create a wallet or prompt during background cover lookups.
        vault = secretstorage.collection.Collection(connection)
        if vault.is_locked():
            if not unlock or vault.unlock(timeout=30):
                raise KeyringError('Unlock your desktop keyring to save or read cover accounts.')
        yield vault
    except KeyringError:
        raise
    except Exception:
        raise KeyringError('The desktop keyring is unavailable. Open or unlock it, then try again.') from None
    finally:
        if connection is not None:
            connection.close()


def read(identity):
    wanted = attributes(identity)
    with collection() as vault:
        for item in vault.search_items(wanted):
            raw = item.get_secret()
            if len(raw) > 65536:
                break
            return raw
    raise KeyringError('The saved cover accounts are unavailable in this desktop keyring.')


def write(identity, raw):
    wanted = attributes(identity)
    with collection(unlock=True) as vault:
        vault.create_item('Retro-Recomp cover accounts', wanted, raw,
                          replace=False, content_type='application/json')


def remove(identity):
    wanted = attributes(identity)
    with collection() as vault:
        for item in vault.search_items(wanted):
            item.delete()
