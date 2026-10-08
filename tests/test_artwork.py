from io import BytesIO
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import subprocess

from PIL import Image

from smsrecomp.artwork import ArtworkError, ICON_SIZES, REPOSITORIES, _get, choose_cover, prepare_icon, resolve_cover
from smsrecomp.cover_settings import defaults
from smsrecomp.paths import boxart_cache_directory


def png():
    image = Image.new("RGBA", (100, 200), (0, 0, 0, 0))
    image.paste((240, 80, 20, 255), (20, 10, 80, 190))
    out = BytesIO(); image.save(out, format="PNG")
    return out.getvalue()


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.art = self.root / "BoxArt"
        self.game = self.root / "build"
        self.game.mkdir()
        self.rom = self.root / "Game (Europe).sms"

    def test_offline_local_cover_and_multisize_transparent_icon(self):
        self.art.mkdir()
        source = self.art / "Game (Europe).png"
        source.write_bytes(png())
        before = source.read_bytes()
        with patch("smsrecomp.artwork._get", side_effect=AssertionError("local art must not use the network")):
            report = prepare_icon(self.game, self.rom, "Game", self.art, online=False)
        self.assertTrue(report["embedded"])
        self.assertEqual(report["source"], "local")
        self.assertEqual(source.read_bytes(), before)
        with Image.open(self.game / "game.ico") as icon:
            self.assertEqual(icon.ico.sizes(), {(n, n) for n in ICON_SIZES})
            image = icon.ico.getimage((256, 256)).copy()
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        bbox = image.getchannel("A").getbbox()
        self.assertEqual(bbox[3] - bbox[1], 256)
        self.assertLess(abs((bbox[2]-bbox[0]) / 256 - 1/3), .015)

    def test_no_fuzzy_matching_between_sequels_and_ambiguous_editions(self):
        names = ["Sonic (USA).png", "Sonic 2 (Europe).png"]
        self.assertEqual(choose_cover(names, "Sonic 2 (Europe)", "Sonic 2"), names[1])
        self.assertIsNone(choose_cover(names, "Sonic 3", "Sonic 3"))
        with self.assertRaises(ArtworkError):
            choose_cover(["Game (USA).png", "Game (Japan).png"], "Game", "Game")
        self.assertEqual(choose_cover(["Game (USA).png", "Game (Japan).png"], "Game (USA, Europe)", "Game"), "Game (USA).png")
        self.assertEqual(choose_cover(["Factory Panic (Europe, Brazil) (En).png",
                                       "Factory Panic (Europe, Brazil).png"],
                                      "Factory Panic (Europe)", "Factory Panic"),
                         "Factory Panic (Europe, Brazil).png")

    def test_online_download_is_cached_and_then_works_offline(self):
        with patch("smsrecomp.artwork._get", return_value=png()) as request:
            report = prepare_icon(self.game, self.rom, "Game", self.art)
        self.assertTrue(report["embedded"])
        self.assertEqual(report["source"], "libretro")
        self.assertIn("Game%20%28Europe%29.png", request.call_args.args[0])
        with patch("smsrecomp.artwork._get", side_effect=AssertionError("cached art must work offline")):
            cached = prepare_icon(self.game, self.rom, "Game", self.art, online=False)
        self.assertEqual(cached["source"], "libretro_cache")
        self.assertEqual(cached["icon_sha256"], report["icon_sha256"])

    def test_automatic_online_cover_beats_local_composition_and_is_reused(self):
        self.art.mkdir()
        source = self.art / 'Game (Europe).png'
        # A valid local mixed-media image also cannot outrank a downloaded box.
        out = BytesIO(); Image.new('RGB', (800, 300), 'blue').save(out, format='PNG')
        source.write_bytes(out.getvalue())
        before = source.read_bytes()
        with patch('smsrecomp.artwork._get', return_value=png()) as client:
            cover = resolve_cover(self.rom, 'Game', self.art, settings=defaults(), emit=lambda _: None)
        self.assertEqual(cover['source'], 'libretro')
        self.assertEqual(cover['style'], 'front')
        self.assertEqual(client.call_count, 1)
        self.assertEqual(source.read_bytes(), before)
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('validated download should be reused')):
            cached = resolve_cover(self.rom, 'Game', self.art, settings=defaults(), emit=lambda _: None)
        self.assertEqual(cached['source'], 'libretro_cache')
        self.assertEqual(cached['data'], cover['data'])

    def test_explicit_selection_wins_even_when_online_is_enabled(self):
        self.art.mkdir()
        selected = self.art / 'Chosen.png'
        selected.write_bytes(png())
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('honor the manual choice')):
            cover = resolve_cover(self.rom, 'Game', self.art, explicit=selected, settings=defaults())
        self.assertEqual(cover['source'], 'explicit')
        self.assertEqual(cover['data'], selected.read_bytes())

    def test_local_fallback_precedes_screenshots_when_online_boxes_fail(self):
        self.art.mkdir()
        selected = self.art / 'Game (Europe).png'
        selected.write_bytes(png())
        requests = []
        def unavailable(url, maximum):
            requests.append(url)
            raise urllib.error.URLError('offline')
        with patch('smsrecomp.artwork._get', side_effect=unavailable):
            cover = resolve_cover(self.rom, 'Game', self.art, settings=defaults(), emit=lambda _: None)
        self.assertEqual(cover['source'], 'local')
        self.assertTrue(requests)
        self.assertTrue(all('Named_Titles' not in url and 'Named_Snaps' not in url for url in requests))

    def test_ambiguous_local_editions_do_not_block_an_exact_online_cover(self):
        self.art.mkdir()
        for name in ('Game (USA).png', 'Game (Japan).png'):
            (self.art / name).write_bytes(png())
        with patch('smsrecomp.artwork._get', return_value=png()):
            cover = resolve_cover(self.rom, 'Game', self.art, settings=defaults(), emit=lambda _: None)
        self.assertEqual(cover['source'], 'libretro')

    def test_separate_data_cache_does_not_write_to_user_boxart(self):
        cache = self.root / "datas/BoxArt"
        with patch("smsrecomp.artwork._get", return_value=png()):
            report = prepare_icon(self.game, self.rom, "Game", self.art, cache_directory=cache)
        self.assertTrue(report["embedded"])
        self.assertFalse(self.art.exists())
        self.assertTrue(Path(report["image"]).is_relative_to(cache))
        with patch("smsrecomp.artwork._get", side_effect=AssertionError("offline cache must not connect")):
            cached = prepare_icon(self.game, self.rom, "Game", self.art, online=False, cache_directory=cache)
        self.assertEqual(cached["source"], "libretro_cache")

    def test_regeneration_reuses_downloads_for_every_console_after_rom_rename(self):
        for system in REPOSITORIES:
            with self.subTest(console=system):
                folder = self.root / system
                folder.mkdir()
                rom = folder / ('Game (Europe).' + system)
                rom.write_bytes(b'authored fixture ' + system.encode())
                build = folder / 'build'; build.mkdir()
                with patch('smsrecomp.paths.data_directory', return_value=self.root / 'datas'):
                    cache = boxart_cache_directory(system)
                self.assertEqual(cache, self.root / 'datas/BoxArt' / system)
                out = BytesIO(); Image.new('RGB', (96, 120), (len(system) * 40, 60, 90)).save(out, format='PNG')
                with patch('smsrecomp.artwork._get', return_value=out.getvalue()) as client:
                    first = prepare_icon(build, rom, 'Game', self.art, cache_directory=cache,
                                         system_id=system, settings=defaults(), emit=lambda _: None)
                self.assertTrue(first['embedded'])
                self.assertEqual(client.call_count, 1)
                saved = next((cache / 'Saved').glob('*.json'))
                record = json.loads(saved.read_text())
                self.assertEqual(record['rom_sha256'], hashlib.sha256(rom.read_bytes()).hexdigest())
                self.assertEqual(record['system_id'], system)
                self.assertFalse(Path(record['image']).is_absolute())
                moved = folder / 'Completely renamed ROM.rom'
                rom.rename(moved)
                regenerated = folder / 'new-build'; regenerated.mkdir()
                settings = defaults()
                settings['accounts']['thegamesdb']['apikey'] = 'fixture-key'
                settings['revision'] = 'changed-fixture-settings'
                with patch('smsrecomp.artwork._get', side_effect=AssertionError('no network on regeneration')), \
                        patch('smsrecomp.artwork.fetch', side_effect=AssertionError('no API on regeneration')), \
                        patch.object(Path, 'rglob', side_effect=AssertionError('saved identity avoids directory scans')):
                    reused = prepare_icon(regenerated, moved, 'New display title', self.art,
                                          cache_directory=cache, system_id=system, settings=settings,
                                          emit=lambda _: None)
                self.assertEqual(reused['source'], 'libretro_cache')
                self.assertEqual(reused['icon_sha256'], first['icon_sha256'])
                self.assertFalse(self.art.exists())

    def test_saved_download_survives_a_move_of_the_converter_cache(self):
        self.rom.write_bytes(b'authored ROM for portable cover cache')
        cache = self.root / 'datas/BoxArt/sms'
        with patch('smsrecomp.artwork._get', return_value=png()):
            original = resolve_cover(self.rom, 'Game', self.art, cache_directory=cache,
                                     settings=defaults(), emit=lambda _: None)
        moved = self.root / 'moved-cache'
        cache.rename(moved)
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('cache paths are relative')):
            reused = resolve_cover(self.rom, 'Game', self.art, cache_directory=moved,
                                   settings=defaults(), emit=lambda _: None)
        self.assertEqual(reused['data'], original['data'])
        self.assertTrue(reused['path'].is_relative_to(moved))

    def test_damaged_saved_images_are_recovered_by_a_new_download(self):
        self.rom.write_bytes(b'authored ROM for cover integrity')
        for corrupt in (b'not an image', png() + b'changed valid image bytes'):
            with self.subTest(corrupt=corrupt[:12]), tempfile.TemporaryDirectory() as temp:
                cache = Path(temp)
                with patch('smsrecomp.artwork._get', return_value=png()):
                    original = resolve_cover(self.rom, 'Game', self.art, cache_directory=cache,
                                             settings=defaults(), emit=lambda _: None)
                original['path'].write_bytes(corrupt)
                with patch('smsrecomp.artwork._get', return_value=png()) as client:
                    repaired = resolve_cover(self.rom, 'Game', self.art, cache_directory=cache,
                                             settings=defaults(), emit=lambda _: None)
                self.assertEqual(client.call_count, 1)
                self.assertEqual(repaired['data'], original['data'])
                self.assertEqual(repaired['path'].read_bytes(), original['data'])

    def test_old_sms_downloads_are_imported_without_changing_them_or_using_other_consoles(self):
        self.rom.write_bytes(b'authored ROM for legacy cover migration')
        base = self.root / 'datas/BoxArt'
        legacy = base / 'Downloaded/Game (Europe).png'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(png())
        sidecar = legacy.with_suffix('.png.json')
        sidecar.write_text(json.dumps({'provider': 'libretro', 'style': 'front',
                                      'sha256': hashlib.sha256(png()).hexdigest()}))
        other = base / 'gg/Downloaded/Game (Europe).png'
        other.parent.mkdir(parents=True)
        other.write_bytes(b'not SMS artwork')
        before = (legacy.read_bytes(), sidecar.read_bytes(), other.read_bytes())
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('old downloads stay usable')), \
                patch('smsrecomp.artwork.fetch', side_effect=AssertionError('no API')):
            cover = resolve_cover(self.rom, 'Game', self.art, cache_directory=base / 'sms',
                                  settings=defaults(), emit=lambda _: None)
        self.assertEqual(cover['source'], 'libretro_cache')
        self.assertEqual(cover['data'], png())
        self.assertTrue(cover['path'].is_relative_to(base / 'sms'))
        self.assertEqual(before, (legacy.read_bytes(), sidecar.read_bytes(), other.read_bytes()))

    def test_empty_offline_cache_creates_no_files(self):
        self.rom.write_bytes(b'authored ROM without artwork')
        cache = self.root / 'absent-cache'
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
            with self.assertRaises(ArtworkError):
                resolve_cover(self.rom, 'Game', self.art, cache_directory=cache,
                              online=False, settings=defaults(), emit=lambda _: None)
        self.assertFalse(cache.exists())
        self.assertFalse(self.art.exists())

    def test_catalog_fallback_keeps_exact_title(self):
        missing = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        catalog = json.dumps({'truncated': False, 'tree': [
            {"type": "blob", "path": "Named_Boxarts/Game (World).png"},
            {"type": "blob", "path": "Named_Boxarts/Game II (World).png"},
            {"type": "blob", "path": "Named_Boxarts/../escape.png"}]}).encode()
        with patch("smsrecomp.artwork._get", side_effect=[missing, missing, catalog, png()]) as request:
            report = prepare_icon(self.game, self.rom, "Game", self.art)
        self.assertTrue(report["embedded"])
        self.assertEqual(Path(report["image"]).name, "Game (World).png")
        self.assertEqual(request.call_count, 4)
        self.assertIn('git/trees/master?recursive=1', request.call_args_list[2].args[0])

    def test_public_server_recovers_a_github_network_failure(self):
        with patch('smsrecomp.artwork._get', side_effect=[urllib.error.URLError('blocked'), png()]) as client:
            report = prepare_icon(self.game, self.rom, 'Game', self.art, emit=lambda text: None)
        self.assertTrue(report['embedded'])
        self.assertEqual(report['media_style'], 'front')
        self.assertIn('thumbnails.libretro.com/', report['url'])
        self.assertEqual(client.call_count, 2)

    def test_trailing_article_matches_the_exact_regional_cover(self):
        names = ['Revenge of Shinobi, The (USA).png',
                 'Revenge of Shinobi, The (USA, Europe).png',
                 'Revenge of Shinobi, The (USA, Europe) (Rev A).png']
        self.assertEqual(choose_cover(names, 'The Revenge of Shinobi (USA)', 'The Revenge of Shinobi'), names[0])

    def test_public_directory_recovers_an_unavailable_github_catalogue(self):
        def request(url, maximum):
            if url.endswith('/Named_Boxarts/'):
                return (b'<a href="../">Parent</a><a href="../escape.png">bad</a>'
                        b'<a href="https://example.test/Game.png">bad</a>'
                        b'<a href="Game%20%28World%29.png">Game</a>'
                        b'<a href="Game%20II%20%28World%29.png">Sequel</a>')
            if 'thumbnails.libretro.com' in url and 'Game%20%28World%29.png' in url:
                return png()
            raise urllib.error.HTTPError(url, 404, 'missing', {}, None)
        with patch('smsrecomp.artwork._get', side_effect=request):
            report = prepare_icon(self.game, self.rom, 'Game', self.art, emit=lambda text: None)
        self.assertTrue(report['embedded'])
        self.assertEqual(Path(report['image']).name, 'Game (World).png')
        self.assertFalse((self.root / 'escape.png').exists())

    def test_title_screen_fallback_is_reused_online_and_offline(self):
        def request(url, maximum):
            if '/Named_Titles/Game%20%28Europe%29.png' in url:
                return png()
            if 'git/trees/' in url:
                return b'{"truncated":false,"tree":[]}'
            raise urllib.error.HTTPError(url, 404, 'missing', {}, None)
        with patch('smsrecomp.artwork._get', side_effect=request) as client:
            report = prepare_icon(self.game, self.rom, 'Game', self.art, emit=lambda text: None)
        self.assertTrue(report['embedded'])
        self.assertEqual(report['media_style'], 'title')
        self.assertFalse(any('/Named_Snaps/' in call.args[0] for call in client.call_args_list))
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
            cached = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, emit=lambda text: None)
        self.assertEqual(cached['media_style'], 'title')
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('regeneration reuses saved artwork')):
            reused = prepare_icon(self.game, self.rom, 'Game', self.art, emit=lambda text: None)
        self.assertEqual(reused['media_style'], 'title')
        self.assertEqual(reused['icon_sha256'], report['icon_sha256'])
        with patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
            offline = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, emit=lambda text: None)
        self.assertEqual(offline['media_style'], 'title')

    def test_snapshot_is_last_resort_and_never_matches_a_sequel(self):
        for correct_title in (True, False):
            with self.subTest(correct_title=correct_title), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                def request(url, maximum):
                    if correct_title and '/Named_Snaps/Game%20%28Europe%29.png' in url:
                        return png()
                    if 'git/trees/' in url:
                        return json.dumps({'truncated': False, 'tree': [
                            {'type': 'blob', 'path': category + '/Game II (Europe).png'}
                            for category in ('Named_Boxarts', 'Named_Titles', 'Named_Snaps')]}).encode()
                    raise urllib.error.HTTPError(url, 404, 'missing', {}, None)
                with patch('smsrecomp.artwork._get', side_effect=request):
                    report = prepare_icon(self.game, self.rom, 'Game', directory, emit=lambda text: None)
                self.assertEqual(report['embedded'], correct_title)
                if correct_title:
                    self.assertEqual(report['media_style'], 'snapshot')

    def test_invalid_remote_image_and_network_failure_do_not_block_conversion(self):
        for failure in (b"<html>not a cover</html>", urllib.error.URLError("offline")):
            with patch("smsrecomp.artwork._get", **({"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure})):
                report = prepare_icon(self.game, self.rom, "Game", self.art)
            self.assertFalse(report["embedded"])
            self.assertIn("warning", report)
            self.assertFalse((self.art / "Downloaded/Game (Europe).png").exists())

    def test_explicit_image_errors_and_no_cover_remove_resource_selection(self):
        with self.assertRaises(ArtworkError):
            prepare_icon(self.game, self.rom, "Game", self.art, explicit=self.root / "missing.png")
        self.art.mkdir()
        (self.art / "Game (Europe).png").write_bytes(png())
        self.assertTrue(prepare_icon(self.game, self.rom, "Game", self.art, online=False)["embedded"])
        with patch("smsrecomp.artwork._get", side_effect=AssertionError("disabled art must not use the network")):
            report = prepare_icon(self.game, self.rom, "Game", self.art, enabled=False)
        self.assertFalse(report["embedded"])
        self.assertNotIn("101 ICON", (self.game / "game_resources.rc").read_text())

    def test_shooting_tag_preserves_source_and_composes_bottom_left_at_each_size(self):
        self.art.mkdir()
        cover = self.art / "Game (Europe).png"
        with Image.open(BytesIO(png())) as blue:
            blue.paste((20,80,240,255), (20,10,80,190))
            buffer = BytesIO(); blue.save(buffer, format="PNG")
        cover.write_bytes(buffer.getvalue())
        before = cover.read_bytes()
        prepare_icon(self.game, self.rom, "Game", self.art, online=False)
        old_icon = (self.game / "game.ico").read_bytes()
        with Image.open(BytesIO(old_icon)) as source:
            originals = {n: source.ico.getimage((n,n)).copy() for n in ICON_SIZES}
        report = prepare_icon(self.game, self.rom, "Game", self.art, online=False, tags=("shooting",))
        self.assertEqual(report["tags"], ["shooting"])
        self.assertNotEqual(old_icon, (self.game / "game.ico").read_bytes())
        self.assertEqual(cover.read_bytes(), before)
        with Image.open(self.game / "game.ico") as source:
            self.assertEqual(source.ico.sizes(), {(n,n) for n in ICON_SIZES})
            for n in ICON_SIZES:
                result = source.ico.getimage((n,n)).convert("RGBA")
                changed = [(x,y) for y in range(n) for x in range(n)
                           if result.getpixel((x,y)) != originals[n].getpixel((x,y))]
                self.assertTrue(changed, n)
                self.assertGreater(min(y for x,y in changed), n//2-1)
                self.assertLess(min(x for x,y in changed), n//2)
                self.assertEqual(result.crop((0,0,n,n//2)).tobytes(), originals[n].crop((0,0,n,n//2)).tobytes())
                if n >= 32:
                    # The outward portion is translucent, without an opaque backing.
                    self.assertTrue(any(0 < result.getpixel((x,y))[3] <= 204 and originals[n].getpixel((x,y))[3] == 0
                                        for y in range(n//2,n) for x in range(n//2)), n)
        # Switching tags off regenerates a clean cover, with no accumulated tag.
        clean = prepare_icon(self.game, self.rom, "Game", self.art, online=False)
        self.assertEqual(clean["tags"], [])
        self.assertEqual((self.game / "game.ico").read_bytes(), old_icon)

    def test_missing_or_invalid_tag_preserves_cover_and_disabled_icons_skip_tags(self):
        self.art.mkdir()
        (self.art / "Game (Europe).png").write_bytes(png())
        for tags in (("shooting",), ("../unknown",)):
            report = prepare_icon(self.game, self.rom, "Game", self.art, online=False,
                                  tags=tags, tag_directory=self.root / "missing-tags")
            self.assertTrue(report["embedded"])
            self.assertEqual(report["tags"], [])
            self.assertIn("tag_warnings", report)
        disabled = prepare_icon(self.game, self.rom, "Game", self.art, enabled=False, tags=("shooting",))
        self.assertFalse(disabled["embedded"])
        self.assertEqual(disabled["tags"], [])
        self.assertNotIn("101 ICON", (self.game / "game_resources.rc").read_text())

    def test_frozen_windows_https_transport_checks_status_and_size(self):
        body = png()
        success = subprocess.CompletedProcess([], 0, body + b"200", b"")
        with patch("smsrecomp.artwork.sys.frozen", True, create=True), patch("smsrecomp.artwork.subprocess.run", return_value=success) as client:
            self.assertEqual(_get("https://example.test/cover.png", len(body)), body)
            self.assertFalse(client.call_args.kwargs.get("shell", False))
            self.assertIn("--proto-redir", client.call_args.args[0])
            self.assertIn("--max-filesize", client.call_args.args[0])
        missing = subprocess.CompletedProcess([], 22, b"404", b"")
        with patch("smsrecomp.artwork.sys.frozen", True, create=True), patch("smsrecomp.artwork.subprocess.run", return_value=missing):
            with self.assertRaises(urllib.error.HTTPError) as error:
                _get("https://example.test/missing.png", 100)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
        too_large = subprocess.CompletedProcess([], 63, b"200", b"")
        with patch("smsrecomp.artwork.sys.frozen", True, create=True), patch("smsrecomp.artwork.subprocess.run", return_value=too_large):
            with self.assertRaises(ArtworkError):
                _get("https://example.test/large.png", 100)


if __name__ == "__main__":
    unittest.main()
