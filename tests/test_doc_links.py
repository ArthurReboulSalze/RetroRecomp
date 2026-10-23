"""Relative documentation links must point at existing files. No ROM is needed."""
from pathlib import Path
import tempfile
import unittest

from tools.check_doc_links import ROOT, check_links


class DocLinkTests(unittest.TestCase):
    def test_public_documentation_links_resolve(self):
        report = check_links(ROOT, public=True)
        self.assertGreater(report.files, 10)
        self.assertEqual(report.broken, [])

    def test_local_documentation_links_resolve(self):
        if not (ROOT / 'docs/PROJECT_STATE.md').exists():
            self.skipTest('local documentation is not present in this checkout')
        report = check_links(ROOT, public=False)
        self.assertEqual(report.broken, [])

    def test_missing_targets_and_html_links_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'docs').mkdir()
            (root / 'docs/GOOD.md').write_text('# Good\n', encoding='utf-8')
            (root / 'README.md').write_text(
                '[ok](docs/GOOD.md) [anchor](docs/GOOD.md#top) <a href="docs/MISSING.md">x</a>\n'
                '![image](MEDIAS/absent.png) [web](https://example.invalid/page.md) [self](#here)\n',
                encoding='utf-8')
            report = check_links(root, public=False)
            self.assertEqual(report.links, 4)
            self.assertEqual(sorted(report.broken),
                             [('README.md', 'MEDIAS/absent.png'), ('README.md', 'docs/MISSING.md')])


if __name__ == '__main__':
    unittest.main()
