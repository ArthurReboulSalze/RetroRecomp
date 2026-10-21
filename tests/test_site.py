"""The website builds from tracked public media and links only to files it ships."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from tools.build_site import MARKER, MEDIA, build
from tools.prepare_publication import PUBLIC_SET


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("src", "href") and value and not value.startswith(("http", "#", "/")):
                self.local.append(value)


class SiteTests(unittest.TestCase):
    def test_media_sources_are_public(self):
        for source, _ in MEDIA.values():
            self.assertIn(source, PUBLIC_SET)

    def test_build_ships_every_local_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "site"
            files = build(output)
            self.assertIn(".nojekyll", files)
            parser = _Links()
            parser.feed((output / "index.html").read_text(encoding="utf-8"))
            self.assertTrue(parser.local)
            for link in parser.local:
                self.assertTrue((output / link).is_file(), link)

    def test_build_refuses_unrelated_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "keep.txt").write_text("user data", encoding="utf-8")
            with self.assertRaises(ValueError):
                build(output)
            self.assertTrue((output / "keep.txt").is_file())
            self.assertFalse((output / MARKER).exists())


if __name__ == "__main__":
    unittest.main()
