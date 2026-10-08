"""Cover discovery, optional official API downloads and Windows box icons.

Names are sent to cover services; ScreenScraper also receives ROM hashes/size.
ROM bytes never leave the machine.
Artwork is optional; downloaded images are validated before entering the cache.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from .paths import ASSETS, boxart_cache_directory
from .cover_settings import load_settings, configured
from .cover_sources import PROVIDERS, CoverServiceError, fetch

REPOSITORIES = {
    'sms': 'libretro-thumbnails/Sega_-_Master_System_-_Mark_III',
    'gg': 'libretro-thumbnails/Sega_-_Game_Gear',
    'gb': 'libretro-thumbnails/Nintendo_-_Game_Boy',
    'nes': 'libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System',
    'md': 'libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis',
    'snes': 'libretro-thumbnails/Nintendo_-_Super_Nintendo_Entertainment_System',
}
REPOSITORY = REPOSITORIES['sms']  # Keep the existing SMS artwork source stable.
FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"}
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
IMAGE_SOURCE_POLICY = 2  # Prefer original/HD provider images over older thumbnails.
PUBLIC_MEDIA = {'Named_Boxarts': 'front', 'Named_Titles': 'title', 'Named_Snaps': 'snapshot'}
# Stable tag IDs are separate from artwork filenames and peripheral detection.
ICON_TAGS = {"shooting": "tag-shooting.png"}
ICON_TAG_LAYOUT = {
    "anchor": "bottom_left_of_visible_cover", "size_ratio": 0.189,
    "minimum_size": 4, "margin_ratio": 0.025, "halo_pixels": 1,
    "opacity": 0.8, "left_overhang_ratio": 0.15, "rendered_per_size": True,
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024
TIMEOUT = 6
_catalog_locks = {key: threading.Lock() for key in REPOSITORIES}


class ArtworkError(ValueError):
    pass


def normalized(name: str, *, base: bool = False) -> str:
    if base:
        name = re.sub(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", "", name)
        # No-Intro names may have several trailing tags, including languages.
        while re.search(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", name):
            name = re.sub(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", "", name)
    # Keep the edition tags while moving No-Intro's trailing article. This
    # allows "The Game (USA)" to select "Game, The (USA)" unambiguously.
    name = re.sub(r'^(.+),\s*(The|A|An)(?=\s*(?:\(|\[|$))', r'\2 \1', name, flags=re.I)
    name = unicodedata.normalize("NFKD", name).casefold()
    return "".join(c for c in name if c.isalnum())


def choose_cover(names: list[str], rom_name: str, title: str) -> str | None:
    """Exact names first, then an unambiguous title. Never fuzzy-match sequels."""
    for query in (rom_name, title):
        matches = [n for n in names if normalized(Path(n).stem) == normalized(query)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ArtworkError("Plusieurs covers portent le même nom ; choisis une image explicitement.")
    keys = {normalized(rom_name, base=True), normalized(title, base=True)} - {""}
    matches = [n for n in names if normalized(Path(n).stem, base=True) in keys]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Keep edition/region preference only when it identifies one image.
        tags = set(re.findall(r"europe|usa|japan|brazil|world|korea", rom_name.casefold()))
        scores = {n: len(tags & set(re.findall(r"europe|usa|japan|brazil|world|korea", n.casefold()))) for n in matches}
        best = max(scores.values())
        winners = [n for n, score in scores.items() if score == best]
        if best and len(winners) == 1:
            return winners[0]
        if best and len(winners) > 1:
            # No-Intro thumbnails may duplicate one regional cover with an
            # extra language suffix. Prefer the least qualified edition only
            # when that rule selects one candidate unambiguously.
            groups = {n: len(re.findall(r"\([^)]*\)|\[[^]]*\]", Path(n).stem)) for n in winners}
            least = min(groups.values())
            shorter = [n for n in winners if groups[n] == least]
            if len(shorter) == 1:
                return shorter[0]
        raise ArtworkError("Plusieurs éditions de la cover correspondent ; choisis une image explicitement.")
    return None


def _image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ArtworkError("Image vide ou supérieure à 8 Mio.")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ArtworkError("Image supérieure à 16 millions de pixels.")
            image = ImageOps.exif_transpose(source).convert("RGBA")
        if not image.getchannel("A").getbbox():
            raise ArtworkError("L'image est entièrement transparente.")
        return image
    except ArtworkError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ArtworkError(f"Image de cover illisible : {exc}") from exc


def _read_image(path: Path) -> bytes:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ArtworkError("Image supérieure à 8 Mio.")
    data = path.read_bytes()
    _image(data)
    return data


def _rom_key(path: Path) -> str | None:
    try:
        with path.open('rb') as rom:
            return hashlib.file_digest(rom, 'sha256').hexdigest()
    except OSError:
        return None


def _saved_cover(directory: Path, key: str | None, system_id: str, prefer3d: bool,
                 online: bool) -> dict | None:
    if key is None:
        return None
    choices = (prefer3d,) if online else (prefer3d, not prefer3d)
    for choice in choices:
        record_path = directory / 'Saved' / (key + ('-box3d.json' if choice else '-front.json'))
        try:
            record = json.loads(record_path.read_text(encoding='utf-8'))
            if (record.get('format') != 1 or record.get('system_id') != system_id
                    or record.get('rom_sha256') != key):
                continue
            relative = Path(record['image'])
            if relative.is_absolute() or not relative.parts or relative.parts[0] != 'Downloaded':
                continue
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()):
                continue
            data = _read_image(path)
            if record['sha256'] != hashlib.sha256(data).hexdigest():
                continue
            if online and not prefer3d and record.get('style') == 'box3d':
                continue
            provider = record.get('provider')
            if provider not in (*PROVIDERS, 'libretro'):
                continue
            return {'path': path, 'data': data, 'source': provider + '_cache',
                    'url': _public_url(record.get('url')), 'style': record.get('style', 'front'),
                    'source_page': _public_url(record.get('source_page'))}
        except (OSError, ArtworkError, ValueError, KeyError, TypeError, AttributeError):
            pass  # Missing or damaged artwork can be recovered by the usual search.
    return None


def _remember_cover(cover: dict, directory: Path, key: str | None, system_id: str,
                    prefer3d: bool) -> dict:
    if key is None or directory.drive.startswith('\\\\'):
        return cover
    provider = cover['source'].removesuffix('_cache')
    if provider not in (*PROVIDERS, 'libretro'):
        return cover
    try:
        relative = cover['path'].resolve().relative_to(directory.resolve())
        if not relative.parts or relative.parts[0] != 'Downloaded':
            return cover
        record = {'format': 1, 'system_id': system_id, 'rom_sha256': key,
                  'image': relative.as_posix(), 'provider': provider,
                  'sha256': hashlib.sha256(cover['data']).hexdigest(),
                  'style': cover.get('style', 'front'), 'url': _public_url(cover.get('url')),
                  'source_page': _public_url(cover.get('source_page'))}
        _atomic(directory / 'Saved' / (key + ('-box3d.json' if prefer3d else '-front.json')),
                json.dumps(record, indent=2).encode())
    except (OSError, ValueError):
        pass  # A read-only cache must not prevent conversion.
    return cover


def _store_download(directory: Path, filename: str, data: bytes, record: dict) -> Path:
    digest = hashlib.sha256(data).hexdigest()
    style = record.get('style', 'front')
    if style not in ('front', 'box3d', 'title', 'snapshot'):
        raise ArtworkError('Unsupported downloaded artwork style.')
    # Different providers/styles cannot overwrite an image used by another ROM.
    path = directory / 'Downloaded' / style / digest / filename
    if not path.is_file() or path.stat().st_size != len(data) or path.read_bytes() != data:
        _atomic(path, data)
    _atomic(path.with_suffix('.png.json'), json.dumps({**record, 'sha256': digest}, indent=2).encode())
    return path


def _downloaded_cover(path: Path) -> dict:
    data = _read_image(path)
    record = {}
    try:
        loaded = json.loads(path.with_suffix('.png.json').read_text(encoding='utf-8'))
        if isinstance(loaded, dict):
            if loaded.get('sha256') != hashlib.sha256(data).hexdigest():
                raise ArtworkError('Cached image does not match its saved checksum.')
            record = loaded
    except ArtworkError:
        raise
    except (OSError, ValueError):
        pass
    provider = record.get('provider', 'libretro')
    if provider not in (*PROVIDERS, 'libretro'):
        provider = 'libretro'
    return {'path': path, 'data': data, 'source': provider + '_cache',
            'url': _public_url(record.get('url')), 'source_page': _public_url(record.get('source_page')),
            'style': record.get('style', 'front' if provider == 'libretro' else 'auto'),
            'checked_box_3d': record.get('checked_box_3d')}


def _download_style(path: Path) -> str:
    try:
        record = json.loads(path.with_suffix('.png.json').read_text(encoding='utf-8'))
        if isinstance(record, dict):
            return record.get('style', 'front')
    except (OSError, ValueError):
        pass
    return 'title' if 'Named_Titles' in path.parts else 'snapshot' if 'Named_Snaps' in path.parts else 'front'


def _atomic(path: Path, data: bytes) -> None:
    if path.drive.startswith('\\\\'):
        raise ArtworkError('Cover downloads and generated artwork must use a local cache.')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _get(url: str, maximum: int) -> bytes:
    # Prefer the built-in Windows HTTPS client in the frozen application;
    # source runs and systems without curl keep the standard Python transport.
    curl = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/curl.exe"
    if os.name == "nt" and getattr(sys, "frozen", False) and curl.is_file():
        result = subprocess.run([str(curl), "--silent", "--show-error", "--fail", "--location",
            "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", str(TIMEOUT),
            "--max-time", str(TIMEOUT * 2), "--max-filesize", str(maximum),
            "--user-agent", "Retro-Recomp/0.7.0 (cover downloader)", "--write-out", "%{http_code}", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT * 2 + 2,
            creationflags=subprocess.CREATE_NO_WINDOW)
        status_bytes = result.stdout[-3:]
        status = int(status_bytes) if status_bytes.isdigit() else 0
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "Réponse HTTP du fournisseur", {}, None)
        if result.returncode == 63 or len(result.stdout) > maximum + 3:
            raise ArtworkError("Réponse du serveur trop volumineuse.")
        if result.returncode or status != 200:
            raise ArtworkError(f"Téléchargement HTTPS impossible (client Windows, code {result.returncode}, HTTP {status}).")
        return result.stdout[:-3]
    request = urllib.request.Request(url, headers={"User-Agent": "Retro-Recomp/0.7.0 (cover downloader)"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ArtworkError("Réponse du serveur trop volumineuse.")
    return data


def _public_base(system_id: str, category: str) -> str:
    console = REPOSITORIES[system_id].split('/')[-1].replace('_', ' ')
    return 'https://thumbnails.libretro.com/' + urllib.parse.quote(console, safe='') + f'/{category}/'


def _public_get(url: str, maximum: int, unavailable: set[str]) -> bytes:
    """Do not repeat a blocked host's timeout for every fallback image type."""
    host = urllib.parse.urlsplit(url).hostname
    if host in unavailable:
        raise ArtworkError('Public artwork server unavailable for this search.')
    try:
        return _get(url, maximum)
    except (ArtworkError, OSError, subprocess.TimeoutExpired) as exc:
        if not isinstance(exc, urllib.error.HTTPError) or exc.code in (403, 429) or exc.code >= 500:
            unavailable.add(host)
        raise


class _DirectoryLinks(HTMLParser):
    """Read only filenames from the public thumbnail server's directory index."""
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            parts = urllib.parse.urlsplit(href)
            if not parts.scheme and not parts.netloc and not parts.query and not parts.fragment:
                self.names.append(urllib.parse.unquote(parts.path))


def _catalog(directory: Path, system_id: str = 'sms', category: str = 'Named_Boxarts',
             unavailable: set[str] | None = None) -> list[str]:
    with _catalog_locks[system_id]:
        return _load_catalog(directory, system_id, category, unavailable)


def _load_catalog(directory: Path, system_id: str, category: str = 'Named_Boxarts',
                  unavailable: set[str] | None = None) -> list[str]:
    unavailable = unavailable if unavailable is not None else set()
    repository = REPOSITORIES[system_id]
    # Contents listings stop at 1,000 files. Game Boy exceeds that limit.
    catalog_url = f"https://api.github.com/repos/{repository}/git/trees/master?recursive=1"
    cache = directory / 'Downloaded' / ('libretro-catalog.json' if category == 'Named_Boxarts'
                                      else f'libretro-{category}-catalog.json')
    try:
        record = json.loads(cache.read_text(encoding="utf-8"))
        if (record.get("repository") == repository and record.get('format') == 2
                and time.time() - record["downloaded_at"] < 7 * 86400):
            return _catalog_names(record["names"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    try:
        record = json.loads(_public_get(catalog_url, 8 * 1024 * 1024, unavailable))
        if not isinstance(record, dict) or record.get('truncated') or not isinstance(record.get('tree'), list):
            raise ArtworkError('Catalogue Libretro indisponible.')
        names = _catalog_names([r['path'].removeprefix(category + '/') for r in record['tree']
            if isinstance(r, dict) and r.get('type') == 'blob' and str(r.get('path', '')).startswith(category + '/')])
    except (ArtworkError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
        parser = _DirectoryLinks()
        parser.feed(_public_get(_public_base(system_id, category), 8 * 1024 * 1024, unavailable).decode('utf-8'))
        names = _catalog_names(parser.names)
        if not names:
            raise ArtworkError('Catalogue public Libretro indisponible.')
    _atomic(cache, json.dumps({"repository": repository, 'format': 2,
                             "downloaded_at": time.time(), "names": names}).encode())
    return names


def _catalog_names(names) -> list[str]:
    if not isinstance(names, list):
        raise ArtworkError("Catalogue de covers invalide.")
    return [n for n in names if isinstance(n, str) and n.lower().endswith(".png")
        and not any(c in n for c in ('/', '\\', '\x00')) and len(n) < 240]


def _download(rom_name: str, title: str, directory: Path, emit, system_id: str = 'sms',
              category: str = 'Named_Boxarts', unavailable: set[str] | None = None) -> tuple[Path, str]:
    unavailable = unavailable if unavailable is not None else set()
    repository = REPOSITORIES[system_id]
    raw_base = f'https://raw.githubusercontent.com/{repository}/master/{category}/'
    bases = (raw_base, _public_base(system_id, category))
    # Libretro replaces filename-restricted characters (including &) with _.
    filename = re.sub(r'[&*/:`<>?\\|"\x00-\x1f]', "_", rom_name) + ".png"
    emit(f'Artwork: searching Libretro ({PUBLIC_MEDIA[category]})…')

    def retrieve(name):
        for base in bases:
            url = base + urllib.parse.quote(name, safe='')
            try:
                return _image(_public_get(url, MAX_IMAGE_BYTES, unavailable)), url
            except (ArtworkError, OSError, subprocess.TimeoutExpired) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
        return None

    result = retrieve(filename)
    if result is None:
        match = choose_cover(_catalog(directory, system_id, category, unavailable), rom_name, title)
        if not match:
            raise ArtworkError('No matching artwork in this Libretro collection.')
        filename = match
        result = retrieve(filename)
    if result is None:
        raise ArtworkError('No usable image from either Libretro server.')
    image, url = result
    # Store validated PNG content, regardless of the server's content-type.
    buffer = BytesIO(); image.save(buffer, format="PNG")
    path = _store_download(directory, filename, buffer.getvalue(), {"provider": "libretro", "url": url,
        'source_page': f'https://github.com/{repository}', 'style': PUBLIC_MEDIA[category],
        "downloaded_utc": datetime.now(timezone.utc).isoformat()})
    return path, url


def resolve_cover(rom_path: Path, title: str, directory: Path, *, explicit: Path | None = None,
                  online: bool = True, cache_directory: Path | None = None,
                  system_id: str = 'sms', settings: dict | None = None, emit=print) -> dict:
    if explicit is not None:
        path = explicit.resolve()
        data = _read_image(path)  # Explicit selection errors must be actionable.
        return {"path": path, "source": "explicit", "url": None, "data": data}
    if cache_directory is None and directory.drive.startswith('\\\\'):
        cache_directory = boxart_cache_directory(system_id)
    settings = settings if settings is not None else load_settings()
    prefer3d = settings.get('box_3d', False) is True
    active = [p for p in ('screenscraper', 'thegamesdb', 'igdb')
              if configured(p, settings.get('accounts', {}).get(p, {}))]
    cached = None
    local = None
    storage = cache_directory or directory
    key = _rom_key(rom_path)

    def remember(cover):
        return _remember_cover(cover, storage, key, system_id, prefer3d)

    saved = _saved_cover(storage, key, system_id, prefer3d, online)
    if saved is not None:
        emit('Box art: reusing the saved download.')
        return saved

    def style_matches(cover):
        return prefer3d or cover.get('style') != 'box3d'

    def fresh(cover):
        if online and not style_matches(cover):
            return False  # A completed search cannot make a 3D box a front cover.
        # Regeneration reuses downloaded art, even after account changes.
        # A new explicit 3D preference may try once for a real box instead.
        return (not online or not prefer3d or cover.get('style') == 'box3d'
                or cover.get('checked_box_3d') is True)

    if cache_directory is not None and cache_directory.resolve() != directory.resolve():
        try:
            cover = resolve_cover(rom_path, title, cache_directory, online=False,
                                  system_id=system_id, settings=settings, emit=emit)
            if cover['source'].endswith('_cache') and fresh(cover):
                return remember(cover)
            if cover['source'].endswith('_cache'):
                cached = cover
        except ArtworkError:
            pass
        # SMS downloads previously lived at BoxArt/Downloaded, beside the
        # newer per-console folders. Import only that directory, never another
        # console's artwork or the read-only ROM/boxart library.
        legacy = cache_directory.parent / 'Downloaded'
        if system_id == 'sms' and cache_directory.name == 'sms' and legacy.is_dir():
            names = [p for p in legacy.rglob('*') if p.is_file() and p.suffix.lower() in FORMATS]
            try:
                match = choose_cover([str(p.relative_to(legacy)) for p in names], rom_path.stem, title)
                if match:
                    cover = _downloaded_cover(legacy / match)
                    if fresh(cover):
                        record = {k: cover.get(k) for k in ('style', 'url', 'source_page')}
                        record['provider'] = cover['source'].removesuffix('_cache')
                        try:
                            cover['path'] = _store_download(storage, cover['path'].name, cover['data'], record)
                        except (ArtworkError, OSError):
                            return cover  # Still use the old download if migration cannot write.
                        return remember(cover)
            except (ArtworkError, OSError):
                pass
    paths = sorted((p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in FORMATS),
        key=lambda p: ("Downloaded" in p.relative_to(directory).parts, str(p).casefold())) if directory.exists() else []
    # Explicit selections were handled above. Automatic local matches may be
    # Batocera mixed-media compositions, so prefer online boxes when enabled.
    for downloaded in (True, False):
        pool = [p for p in paths if ("Downloaded" in p.relative_to(directory).parts) == downloaded]
        match = None
        groups = (('box3d', 'front', 'auto', 'title', 'snapshot') if prefer3d else
                  ('front', 'auto', 'box3d', 'title', 'snapshot')) if downloaded else (None,)
        for category in groups:
            candidates = [p for p in pool if not downloaded or
                (_download_style(p) == category and (not online or prefer3d or category != 'box3d'))]
            try:
                match = choose_cover([str(p.relative_to(directory)) for p in candidates], rom_path.stem, title)
            except ArtworkError:
                if not online:
                    raise
                emit('Box art: ambiguous local editions; continuing the online search.')
                continue
            if match:
                break
        if match:
            path = directory / match
            try:
                data = _read_image(path)
            except (OSError, ArtworkError) as exc:
                emit(f"Cover locale inutilisable : {exc}")
                continue
            if downloaded:
                try:
                    cover = _downloaded_cover(path)
                except ArtworkError:
                    continue
            else:
                cover = {'path': path, 'source': 'local', 'url': None, 'data': data, 'style': 'auto'}
            if not downloaded and online:
                local = cover
                continue
            if not downloaded or fresh(cover):
                return remember(cover)
            cached = cover
    if online:
        for provider in active:
            account = settings.get('accounts', {}).get(provider, {})
            if not configured(provider, account):
                continue
            emit(f"Box art: searching {PROVIDERS[provider][0]}…")
            try:
                cover = fetch(provider, account, rom_path, title, system_id,
                              prefer3d=prefer3d, normalize=normalized)
                if cover is None:
                    continue
                if not prefer3d and cover.style == 'box3d':
                    emit(f"Box art · {PROVIDERS[provider][0]}: no front cover; trying the next source.")
                    continue
                image = _image(cover.data)
                buffer = BytesIO(); image.save(buffer, format='PNG')
                filename = re.sub(r'[&*/:`<>?\\|"\x00-\x1f]', '_', rom_path.stem) + '.png'
                data = buffer.getvalue()
                record = {'provider': provider, 'source_page': _public_url(cover.source_page),
                          'url': _public_url(cover.url), 'style': cover.style,
                          'checked_sources': active, 'settings_revision': settings.get('revision', ''),
                          'checked_box_3d': prefer3d,
                          'checked_image_policy': IMAGE_SOURCE_POLICY,
                          'sha256': hashlib.sha256(data).hexdigest(),
                          'downloaded_utc': datetime.now(timezone.utc).isoformat()}
                path = _store_download(storage, filename, data, record)
                return remember({'path': path, 'source': provider, 'data': data, 'url': record['url'],
                                 'source_page': record['source_page'], 'style': cover.style})
            except CoverServiceError as exc:
                emit(f"Box art · {PROVIDERS[provider][0]}: {exc}")
            except (ArtworkError, OSError):
                emit(f"Box art · {PROVIDERS[provider][0]}: unusable image; trying the next source.")
        if (cached is not None and cached.get('style') not in ('title', 'snapshot')
                and style_matches(cached)):
            _checked_cache(cached['path'], active, settings)
            return remember(cached)
        unavailable = set()
        for category, style in PUBLIC_MEDIA.items():
            try:
                path, url = _download(rom_path.stem, title, cache_directory or directory,
                                      emit, system_id, category, unavailable)
            except (ArtworkError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                # Only boxes matching the requested style beat a screenshot.
                # Keep an incompatible 3D image on disk for offline/3D use.
                if cached is not None and style_matches(cached) and (
                        cached.get('style') not in ('title', 'snapshot') or
                        (category == 'Named_Titles' and cached.get('style') == 'title')):
                    _checked_cache(cached['path'], active, settings)
                    return remember(cached)
                if category == 'Named_Boxarts' and local is not None:
                    emit('Box art: online boxes unavailable; using the matching local image.')
                    return local
                continue
            _checked_cache(path, active, settings)
            return remember({'path': path, 'source': 'libretro', 'url': url, 'data': _read_image(path),
                             'style': style, 'source_page': f'https://github.com/{REPOSITORIES[system_id]}'})
        if cached is not None and style_matches(cached):
            return remember(cached)
        raise ArtworkError('No box art, title screen or game image found for this title.')
    raise ArtworkError("Aucune cover locale correspondante ; téléchargement désactivé.")


def _checked_cache(path, active, settings):
    if path.drive.startswith('\\\\'):
        return  # Never update sidecars in read-only network source collections.
    record_path = path.with_suffix('.png.json')
    try:
        record = json.loads(record_path.read_text(encoding='utf-8'))
        record.update(checked_sources=active, settings_revision=settings.get('revision', ''),
                      checked_box_3d=settings.get('box_3d', False) is True,
                      checked_image_policy=IMAGE_SOURCE_POLICY)
        record['url'] = _public_url(record.get('url'))
        record['source_page'] = _public_url(record.get('source_page'))
        _atomic(record_path, json.dumps(record, indent=2).encode())
    except (OSError, ValueError, AttributeError):
        pass  # Provenance bookkeeping must not invalidate an otherwise good image.


def _public_url(url) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if (parsed.scheme != 'https' or parsed.username or parsed.password or
            any(key.casefold() in ('apikey', 'devid', 'devpassword', 'ssid', 'sspassword',
                                  'client_id', 'client_secret', 'access_token', 'token')
                for key, value in urllib.parse.parse_qsl(parsed.query))):
        return None
    return url


def icon_image(image: Image.Image, size: int) -> Image.Image:
    """Fit the source directly to one resource size, preserving its silhouette."""
    fitted = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
    square = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    square.alpha_composite(fitted, ((size-fitted.width)//2, (size-fitted.height)//2))
    return square


def tagged_icon_image(square: Image.Image, size: int, tags: list[Image.Image]) -> Image.Image:
    """Compose a discreet badge at the cover's bottom-left, at each ICO size."""
    image = square.resize((size, size), Image.Resampling.LANCZOS)
    visible = image.getchannel("A").point(lambda a: 255 if a >= 32 else 0).getbbox()
    if not visible:
        return image
    # 30% smaller than the initial 27% badge, rounded to whole icon pixels.
    edge = max(ICON_TAG_LAYOUT["minimum_size"], round(size * ICON_TAG_LAYOUT["size_ratio"]))
    margin = max(1, round(size * ICON_TAG_LAYOUT["margin_ratio"]))
    y = visible[3] - margin
    for tag in tags:
        badge = ImageOps.contain(tag, (edge, edge), Image.Resampling.LANCZOS)
        halo = Image.new("RGBA", (badge.width+2, badge.height+2), (255, 255, 255, 0))
        mask = Image.new("L", halo.size)
        mask.paste(badge.getchannel("A"), (1, 1))
        halo.putalpha(mask.filter(ImageFilter.MaxFilter(3)))
        halo.alpha_composite(badge, (1, 1))
        # Fade the entire badge, including the halo, leaving the cover intact.
        halo.putalpha(halo.getchannel("A").point(lambda a: round(a * ICON_TAG_LAYOUT["opacity"])))
        x = max(0, visible[0] - round(halo.width * ICON_TAG_LAYOUT["left_overhang_ratio"]))
        y -= halo.height
        image.alpha_composite(halo, (x, max(0, y)))
        y -= margin
    return image


def prepare_icon(game: Path, rom_path: Path, title: str, directory: Path, *, explicit: Path | None = None,
                 online: bool = True, enabled: bool = True, cache_directory: Path | None = None,
                 tags: tuple[str, ...] = (), tag_directory: Path | None = None,
                 system_id: str = 'sms', settings: dict | None = None, emit=print) -> dict:
    resource, icon = game / "game_resources.rc", game / "game.ico"
    # Always replace the generated resource description, including when a
    # formerly covered game is reconverted with --no-cover or without its art.
    resource.write_text("/* Generated optional game icon. */\n", encoding="ascii")
    report = {"embedded": False, "source": "disabled" if not enabled else "missing",
        "online_enabled": online, "image": None, "url": None, "tags": [], "requested_tags": list(tags)}
    if not enabled:
        return report
    try:
        settings = settings if settings is not None else load_settings()
        cover = resolve_cover(rom_path, title, directory, explicit=explicit, online=online,
                              cache_directory=cache_directory, system_id=system_id, settings=settings, emit=emit)
        image = _image(cover["data"])
        original_size = list(image.size)
        style = cover.get('style', 'auto')
        # A real box is used as supplied. A front remains a front: no invented
        # spine, perspective, border or decoration. Trim empty alpha only.
        image = image.crop(image.getchannel("A").getbbox())
        visible_size = list(image.size)
        tag_images, tag_sources = [], []
        for tag_id in dict.fromkeys(tags):
            try:
                filename = ICON_TAGS.get(tag_id)
                if filename is None:
                    raise ArtworkError(f"Tag inconnu : {tag_id}")
                data = _read_image((tag_directory or ASSETS / "assets") / filename)
                tag = _image(data)
                tag_images.append(tag.crop(tag.getchannel("A").getbbox()))
                tag_sources.append({"id": tag_id, "asset_sha256": hashlib.sha256(data).hexdigest()})
            except (ArtworkError, OSError) as exc:
                report.setdefault("tag_warnings", []).append(str(exc))
                emit(f"Tag d'icône indisponible : {exc}. La cover reste utilisée.")
        buffer = BytesIO()
        # Each size comes straight from the full-resolution source, never from
        # an intermediate 256px thumbnail. Tags are composed at each size too.
        frames = [tagged_icon_image(icon_image(image, n), n, tag_images)
                  if tag_images else icon_image(image, n) for n in ICON_SIZES]
        square = frames[-1]
        square.save(buffer, format="ICO", sizes=[(n, n) for n in ICON_SIZES], append_images=frames[:-1])
        if tag_images:
            report.update(tags=[s["id"] for s in tag_sources], tag_assets=tag_sources,
                          tag_layout=dict(ICON_TAG_LAYOUT))
        _atomic(icon, buffer.getvalue())
        # Unicode RC input encoded explicitly; filename is generated, fixed and
        # relative to GAME_DIR so user image paths never enter RC source text.
        resource.write_text('#pragma code_page(65001)\n101 ICON "game.ico"\n', encoding="utf-8")
        square.save(game / "game-icon.png")
        report.update(embedded=True, source=cover["source"], image=str(cover["path"]), url=cover["url"],
            image_sha256=hashlib.sha256(cover["data"]).hexdigest(), image_size=original_size,
            visible_image_size=visible_size, largest_icon_size=max(ICON_SIZES),
            source_resolution_sufficient=max(visible_size) >= max(ICON_SIZES),
            icon_sha256=hashlib.sha256(buffer.getvalue()).hexdigest(), sizes=list(ICON_SIZES),
            resource_id=101, fit="preserve_aspect_trim_transparent_margins")
        report.update(source_page=cover.get('source_page'),
                      media_style=style,
                      box_style='source_3d' if style == 'box3d' else 'original')
        emit(f"Icône : {cover['path'].name} ({cover['source']}).")
        if style in ('title', 'snapshot'):
            emit(f'Icon fallback: {"title screen" if style == "title" else "in-game image"}; no box art found.')
        if report["tags"]:
            emit("Tags de l'icône : " + ", ".join(report["tags"]) + ".")
    except (ArtworkError, OSError, urllib.error.URLError, ValueError, subprocess.TimeoutExpired) as exc:
        if explicit is not None:
            raise ArtworkError(f"Impossible d'utiliser la cover choisie : {exc}") from exc
        report["warning"] = str(exc)
        emit(f"Icône de cover indisponible : {str(exc).rstrip('.')}. La conversion continue.")
    return report
