"""ROM-free, pinned cartridge descriptors; identification needs no toolchain."""
from functools import lru_cache
import hashlib
import json
from .paths import ASSETS

RESOURCE = 'assets/neogeo-catalogue.json'
SHA256 = '2e1df16d21ea9eab1705c9cb6baa2eae5ee65974f800da6de12ee9b502f7d80a'
LOADER = 'ef0f9bd94e31689def44b49e0f8351e0206b622d'


@lru_cache(maxsize=1)
def catalogue() -> list[dict]:
    with (ASSETS / RESOURCE).open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('Neo Geo cartridge catalogue failed its integrity check.')
    data = json.loads(raw)
    if data.get('schema') != 1 or data.get('loader') != LOADER or not isinstance(data.get('games'), list):
        raise ValueError('Invalid Neo Geo cartridge catalogue.')
    return data['games']
