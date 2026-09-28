"""Cover discovery, optional Libretro download and conversion-time Windows icons.

Only names are sent to the thumbnail server. ROM data never leaves the machine.
Artwork is optional; downloaded images are validated before entering the cache.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
import time
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from .paths import ASSETS

REPOSITORIES = {
    'sms': 'libretro-thumbnails/Sega_-_Master_System_-_Mark_III',
    'gg': 'libretro-thumbnails/Sega_-_Game_Gear',
    'gb': 'libretro-thumbnails/Nintendo_-_Game_Boy',
    'nes': 'libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System',
}
REPOSITORY = REPOSITORIES['sms']  # Keep the existing SMS artwork source stable.
FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"}
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
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


class ArtworkError(ValueError):
    pass


def normalized(name: str, *, base: bool = False) -> str:
    if base:
        name = re.sub(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", "", name)
        # No-Intro names may have several trailing tags, including languages.
        while re.search(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", name):
            name = re.sub(r"\s*(?:\([^)]*\)|\[[^]]*\])\s*$", "", name)
        name = re.sub(r"^(.+),\s*(The|A|An)$", r"\2 \1", name, flags=re.I)
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


def _atomic(path: Path, data: bytes) -> None:
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


def _catalog(directory: Path, system_id: str = 'sms') -> list[str]:
    repository = REPOSITORIES[system_id]
    catalog_url = f"https://api.github.com/repos/{repository}/contents/Named_Boxarts"
    cache = directory / "Downloaded/libretro-catalog.json"
    try:
        record = json.loads(cache.read_text(encoding="utf-8"))
        if record.get("repository") == repository and time.time() - record["downloaded_at"] < 7 * 86400:
            return _catalog_names(record["names"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    rows = json.loads(_get(catalog_url, 2 * 1024 * 1024))
    if not isinstance(rows, list):
        raise ArtworkError("Catalogue Libretro indisponible.")
    names = _catalog_names([r.get("name", "") for r in rows if isinstance(r, dict) and r.get("type") == "file"])
    _atomic(cache, json.dumps({"repository": repository, "downloaded_at": time.time(), "names": names}).encode())
    return names


def _catalog_names(names) -> list[str]:
    if not isinstance(names, list):
        raise ArtworkError("Catalogue de covers invalide.")
    return [n for n in names if isinstance(n, str) and n.lower().endswith(".png")
        and not any(c in n for c in ('/', '\\', '\x00')) and len(n) < 240]


def _download(rom_name: str, title: str, directory: Path, emit, system_id: str = 'sms') -> tuple[Path, str]:
    repository = REPOSITORIES[system_id]
    raw_base = f"https://raw.githubusercontent.com/{repository}/master/Named_Boxarts/"
    # Libretro replaces filename-restricted characters (including &) with _.
    filename = re.sub(r'[&*/:`<>?\\|"\x00-\x1f]', "_", rom_name) + ".png"
    url = raw_base + urllib.parse.quote(filename, safe="")
    emit("Cover locale absente : recherche sur Libretro…")
    try:
        data = _get(url, MAX_IMAGE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        exc.close()
        match = choose_cover(_catalog(directory, system_id), rom_name, title)
        if not match:
            raise ArtworkError("Aucune cover Libretro trouvée pour ce titre.")
        filename = match
        url = raw_base + urllib.parse.quote(filename, safe="")
        data = _get(url, MAX_IMAGE_BYTES)
    image = _image(data)
    # Store validated PNG content, regardless of the server's content-type.
    buffer = BytesIO(); image.save(buffer, format="PNG")
    path = directory / "Downloaded" / filename
    _atomic(path, buffer.getvalue())
    _atomic(path.with_suffix(".png.json"), json.dumps({"provider": "libretro", "url": url,
        "source_page": f"https://github.com/{repository}", "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
        "downloaded_utc": datetime.now(timezone.utc).isoformat()}, indent=2).encode())
    return path, url


def resolve_cover(rom_path: Path, title: str, directory: Path, *, explicit: Path | None = None,
                  online: bool = True, cache_directory: Path | None = None,
                  system_id: str = 'sms', emit=print) -> dict:
    if explicit is not None:
        path = explicit.resolve()
        data = _read_image(path)  # Explicit selection errors must be actionable.
        return {"path": path, "source": "explicit", "url": None, "data": data}
    paths = sorted((p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in FORMATS),
        key=lambda p: ("Downloaded" in p.relative_to(directory).parts, str(p).casefold())) if directory.exists() else []
    # Manual covers take priority over downloaded editions of the same game.
    for downloaded in (False, True):
        pool = [p for p in paths if ("Downloaded" in p.relative_to(directory).parts) == downloaded]
        match = choose_cover([str(p.relative_to(directory)) for p in pool], rom_path.stem, title)
        if match:
            path = directory / match
            try:
                data = _read_image(path)
            except (OSError, ArtworkError) as exc:
                emit(f"Cover locale inutilisable : {exc}")
                continue
            url = None
            if downloaded:
                try:
                    record = json.loads(path.with_suffix(".png.json").read_text())
                    if record.get("sha256") == hashlib.sha256(data).hexdigest():
                        url = record.get("url")
                except (OSError, ValueError, AttributeError):
                    pass
            return {"path": path, "source": "libretro_cache" if downloaded else "local", "url": url, "data": data}
    if cache_directory is not None and cache_directory.resolve() != directory.resolve():
        try:
            return resolve_cover(rom_path, title, cache_directory, online=False,
                                 system_id=system_id, emit=emit)
        except ArtworkError:
            pass
    if online:
        path, url = _download(rom_path.stem, title, cache_directory or directory, emit, system_id)
        return {"path": path, "source": "libretro", "url": url, "data": _read_image(path)}
    raise ArtworkError("Aucune cover locale correspondante ; téléchargement désactivé.")


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
                 system_id: str = 'sms', emit=print) -> dict:
    resource, icon = game / "game_resources.rc", game / "game.ico"
    # Always replace the generated resource description, including when a
    # formerly covered game is reconverted with --no-cover or without its art.
    resource.write_text("/* Generated optional game icon. */\n", encoding="ascii")
    report = {"embedded": False, "source": "disabled" if not enabled else "missing",
        "online_enabled": online, "image": None, "url": None, "tags": [], "requested_tags": list(tags)}
    if not enabled:
        return report
    try:
        cover = resolve_cover(rom_path, title, directory, explicit=explicit, online=online,
                              cache_directory=cache_directory, system_id=system_id, emit=emit)
        image = _image(cover["data"])
        original_size = list(image.size)
        # Trim only empty alpha margins, retaining the entire box and its ratio.
        image = image.crop(image.getchannel("A").getbbox())
        image = ImageOps.contain(image, (256, 256), Image.Resampling.LANCZOS)
        square = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        square.alpha_composite(image, ((256-image.width)//2, (256-image.height)//2))
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
        if tag_images:
            frames = [tagged_icon_image(square, n, tag_images) for n in ICON_SIZES]
            square = frames[-1]
            # Explicit frames prevent the 16/32px badge halo being downsampled
            # from the largest image. Preserve the badge at every resource size.
            square.save(buffer, format="ICO", sizes=[(n, n) for n in ICON_SIZES], append_images=frames[:-1])
            report.update(tags=[s["id"] for s in tag_sources], tag_assets=tag_sources,
                          tag_layout=dict(ICON_TAG_LAYOUT))
        else:
            square.save(buffer, format="ICO", sizes=[(n, n) for n in ICON_SIZES])
        _atomic(icon, buffer.getvalue())
        # Unicode RC input encoded explicitly; filename is generated, fixed and
        # relative to GAME_DIR so user image paths never enter RC source text.
        resource.write_text('#pragma code_page(65001)\n101 ICON "game.ico"\n', encoding="utf-8")
        square.save(game / "game-icon.png")
        report.update(embedded=True, source=cover["source"], image=str(cover["path"]), url=cover["url"],
            image_sha256=hashlib.sha256(cover["data"]).hexdigest(), image_size=original_size,
            icon_sha256=hashlib.sha256(buffer.getvalue()).hexdigest(), sizes=list(ICON_SIZES),
            resource_id=101, fit="preserve_aspect_trim_transparent_margins")
        emit(f"Icône : {cover['path'].name} ({cover['source']}).")
        if report["tags"]:
            emit("Tags de l'icône : " + ", ".join(report["tags"]) + ".")
    except (ArtworkError, OSError, urllib.error.URLError, ValueError, subprocess.TimeoutExpired) as exc:
        if explicit is not None:
            raise ArtworkError(f"Impossible d'utiliser la cover choisie : {exc}") from exc
        report["warning"] = str(exc)
        emit(f"Icône de cover indisponible : {str(exc).rstrip('.')}. La conversion continue.")
    return report
