"""tools/ab_conversion.py refuses a folder that already holds links (a worktree with its .deps junctions): it detaches every link of a
tree when it ends, which left the worktree without them."""
import tempfile
import unittest
from pathlib import Path

from tools import ab_conversion as ab


class FolderGuardTests(unittest.TestCase):
    def test_a_folder_with_links_is_refused_and_the_message_says_to_pass_a_git_ref(self):
        with tempfile.TemporaryDirectory() as base:
            source = Path(base) / 'shared'
            source.mkdir()
            tree = Path(base) / 'tree'
            (tree / '.deps').mkdir(parents=True)
            ab.link(source, tree / '.deps' / 'SDL')
            try:
                with self.assertRaises(SystemExit) as raised:
                    ab.prepare_tree(str(tree), 'a', Path(base) / 'work', Path(base) / 'deps', None)
                self.assertIn('git ref', str(raised.exception))
                self.assertIn('SDL', str(raised.exception))
                self.assertTrue((tree / '.deps' / 'SDL').exists())      # nothing was touched
            finally:
                ab.unlink(tree / '.deps' / 'SDL')


class KeptBuildTests(unittest.TestCase):
    """The kept build folders a side is compared by: without one, the tool counts the conversion as failed (it said « FAILED » on
    every MSX conversion until 21 Nov 2026, the MSX's work folder `.build/msx/<cartridge>-<bios>` being unknown to it)."""

    def test_every_machine_folder_form_is_found_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as base:
            tree = Path(base)
            build = tree / '.build'
            kept = ('sonic', 'ng-mslug', 'md-sor2', 'snes-smw', 'cps1/sf2-0123456789ab', 'msx/0123456789ab-89abcdef',
                    'x68/win-llvm/0123456789ab')
            for name in kept:
                (build / name).mkdir(parents=True)
            (build / 'sonic' / 'rom.sms').write_bytes(b'')
            (build / 'msx' / 'entry.lock').write_bytes(b'')        # a file beside the work folders, not one of them
            (build / 'notes').mkdir()                               # a folder of no machine: left out
            found = [path.relative_to(build).as_posix() for path in ab.kept_builds(tree)]
            self.assertEqual(found, sorted(kept))

    def test_an_msx_work_folder_alone_is_a_kept_build(self):
        with tempfile.TemporaryDirectory() as base:
            work = Path(base) / '.build' / 'msx' / '0123456789ab-89abcdef'
            (work / 'generated').mkdir(parents=True)
            (work / 'generated' / 'bodies.c').write_text('int x;\n', encoding='utf-8')
            self.assertEqual(ab.kept_builds(Path(base)), [work])

    def test_banked_sources_compares_without_the_tree_path(self):
        # The banked Z80 chain names the BIOS files by their absolute path in the tree: two trees give the same fingerprint.
        with tempfile.TemporaryDirectory() as base:
            prints = []
            for label in ('a', 'b'):
                tree = Path(base) / label
                work = tree / '.build' / 'msx' / '0123456789ab-89abcdef'
                work.mkdir(parents=True)
                listing = work / 'banked.sources'
                listing.write_text(f"{(work / 'bios.rom').resolve()}\n{(work / 'sub.rom').resolve()}\n", encoding='utf-8')
                prints.append(ab.fingerprint(listing, ab.Normaliser({tree: '<TREE>'})))
            self.assertEqual(prints[0], prints[1])


if __name__ == '__main__':
    unittest.main()
