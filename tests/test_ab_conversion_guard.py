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


if __name__ == '__main__':
    unittest.main()
