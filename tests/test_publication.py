"""Publication guards use synthetic data; no ROMs or credentials are needed."""
from pathlib import Path
import tempfile
import unittest

from tools.prepare_publication import PUBLIC_FILES, check_public_file, audit_staged


class PublicationTests(unittest.TestCase):
    def test_audit_cli_validates_knowledge_without_cwd_or_pythonpath(self):
        import gzip
        import json
        import subprocess
        import sys

        script = Path(__file__).resolve().parents[1] / 'tools/prepare_publication.py'
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / 'synthetic-public'
            for name in PUBLIC_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'synthetic public fixture\n')
            knowledge = source / 'assets/compilation-knowledge.json.gz'
            knowledge.write_bytes(gzip.compress(json.dumps({'schema': 1, 'consoles': {}}).encode()))
            (source / 'assets/cover-references.json').write_text(
                json.dumps({'format': 1, 'entries': []}), encoding='utf-8')
            report = folder / 'audit.json'
            result = subprocess.run([sys.executable, '-I', str(script), '--source', str(source),
                                     '--report', str(report)], cwd=folder, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report.read_text())['source']['count'], len(PUBLIC_FILES))

    def test_game_files_and_private_histories_are_not_public(self):
        for name in ("ROMS/game.sms", "boxart/game.png", "Export/game.exe",
                     "profiles/12345678.manifest", "docs/PROJECT_STATE.md",
                     ".env", "MEDIAS/extra.png"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                check_public_file(name, b"synthetic private fixture")

    def test_only_approved_branding_is_allowed(self):
        check_public_file("MEDIAS/RetroRecomp_ban.png", b"synthetic banner")
        check_public_file("MEDIAS/TAG_SHOOTING.png", b"synthetic tag")
        check_public_file("assets/tag-shooting.png", b"synthetic tag")
        with self.assertRaises(ValueError):
            check_public_file("assets/Retro-Recomp-logo.png", b"stale image")

    def test_secrets_are_rejected_without_echoing_the_value(self):
        fake = "gh" + "p_" + "x" * 36
        with self.assertRaises(ValueError) as error:
            check_public_file("README.md", fake.encode())
        self.assertNotIn(fake, str(error.exception))

    def test_personal_paths_are_rejected(self):
        drive = "D:/"
        network = "\\\\" + ".".join(("10", "0", "0", "1")) + "\\synthetic"
        for text in (drive + "Users/synthetic/cache", drive + "Projects/synthetic/build",
                     network):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_public_file("README.md", text.encode())

    def test_git_index_audit_reads_staged_not_working_tree(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git("init", "-q")
            path = root / "README.md"
            path.write_text("sk-" + "x" * 36, encoding="utf-8")
            git("add", "README.md")
            path.write_text("clean working tree", encoding="utf-8")
            with self.assertRaises(ValueError):
                audit_staged(root)
            git("add", "README.md")
            self.assertEqual(audit_staged(root)["staged_count"], 1)


if __name__ == "__main__":
    unittest.main()
