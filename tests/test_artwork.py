from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import subprocess

from PIL import Image

from smsrecomp.artwork import ArtworkError, ICON_SIZES, _get, choose_cover, prepare_icon


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

    def test_local_priority_and_multisize_transparent_icon(self):
        self.art.mkdir()
        source = self.art / "Game (Europe).png"
        source.write_bytes(png())
        before = source.read_bytes()
        with patch("smsrecomp.artwork._get", side_effect=AssertionError("local art must not use the network")):
            report = prepare_icon(self.game, self.rom, "Game", self.art)
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

    def test_catalog_fallback_keeps_exact_title(self):
        missing = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        catalog = json.dumps([{"type": "file", "name": "Game (World).png"},
            {"type": "file", "name": "Game II (World).png"},
            {"type": "file", "name": "../escape.png"}]).encode()
        with patch("smsrecomp.artwork._get", side_effect=[missing, catalog, png()]) as request:
            report = prepare_icon(self.game, self.rom, "Game", self.art)
        self.assertTrue(report["embedded"])
        self.assertEqual(Path(report["image"]).name, "Game (World).png")
        self.assertEqual(request.call_count, 3)

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
        self.assertTrue(prepare_icon(self.game, self.rom, "Game", self.art)["embedded"])
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
