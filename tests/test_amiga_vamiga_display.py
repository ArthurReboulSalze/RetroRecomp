import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import amiga_conversion, amiga_knowledge, amiga_vamiga, amiga_vamiga_display

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps' / 'vamiga' / 'Core'


class PictureChangesTests(unittest.TestCase):
    # The line between a picture change and a generator source: `amiga_vamiga_display` is not pinned (a path cannot notice which colour a
    # pixel gets), so it may only change the files and functions listed in PICTURE_FILES, and never one `amiga_vamiga` changes for the CPU.
    def test_the_module_is_outside_the_generator_pins_and_touches_picture_files_only(self):
        self.assertNotIn('retrorecomp/amiga_vamiga_display.py', amiga_knowledge.GENERATOR_SOURCES)
        self.assertIn('retrorecomp/amiga_vamiga.py', amiga_knowledge.GENERATOR_SOURCES)
        self.assertTrue(amiga_vamiga_display.REPLACEMENTS)
        for rel, old, new in amiga_vamiga_display.REPLACEMENTS:
            self.assertIn(rel, amiga_vamiga_display.PICTURE_FILES, rel)
            self.assertTrue(rel.startswith('Components/Denise/'), rel)
            self.assertNotEqual(old, new)
            self.assertIn('Retro-Recomp modification (MPL-2.0, like this file)', new, rel)
        for rel in amiga_vamiga_display.PICTURE_FILES:
            self.assertFalse(any(part in rel for part in ('CPU', 'Moira', 'Memory', 'Agnus', 'Paula', 'CIA')), rel)

    def test_the_build_stamp_moves_with_a_picture_change(self):
        base = amiga_vamiga_display.adaptation_digest()
        self.assertNotEqual(base, amiga_vamiga.adaptation_digest())
        stamp = amiga_conversion.sdk_stamp()
        kept = list(amiga_vamiga_display.REPLACEMENTS)
        try:
            amiga_vamiga_display.REPLACEMENTS.append(('Components/Denise/Denise.cpp', 'a', 'b'))
            self.assertNotEqual(amiga_vamiga_display.adaptation_digest(), base)
            self.assertNotEqual(amiga_conversion.sdk_stamp(), stamp)
        finally:
            amiga_vamiga_display.REPLACEMENTS[:] = kept
        self.assertEqual(amiga_conversion.sdk_stamp(), stamp)

    @unittest.skipUnless(PINNED.is_dir(), 'the pinned vAmiga is not in this tree')
    def test_each_replacement_sits_in_its_listed_function_and_the_tree_is_made_once_per_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            core = amiga_vamiga_display.adapt(PINNED.parent, target)
            marker = core / amiga_vamiga_display.MARKER
            self.assertEqual(json.loads(marker.read_text(encoding='utf-8'))['adaptation'], amiga_vamiga_display.adaptation_digest())
            for rel, old, new in amiga_vamiga_display.REPLACEMENTS:
                text = (core / rel).read_text(encoding='utf-8')
                self.assertEqual(text.count(new), 1, rel)
                at = text.index(new)
                # The nearest function header above the replacement is one the module lists for this file.
                header = max(amiga_vamiga_display.PICTURE_FILES[rel], key=lambda name: text.rfind(name, 0, at))
                start = text.rfind(header, 0, at)
                self.assertGreaterEqual(start, 0, rel)
                self.assertNotIn('\n}\n', text[start:at], f'{rel}: the replacement is outside {header}')
            # A second call changes nothing; a tree of another digest is made again from the checkout, never patched twice.
            stamp = marker.stat().st_mtime_ns
            self.assertEqual(amiga_vamiga_display.adapt(PINNED.parent, target), core)
            self.assertEqual(marker.stat().st_mtime_ns, stamp)
            marker.write_text('{"adaptation": "other"}\n', encoding='utf-8')
            core = amiga_vamiga_display.adapt(PINNED.parent, target)
            for rel, old, new in amiga_vamiga_display.REPLACEMENTS:
                self.assertEqual((core / rel).read_text(encoding='utf-8').count(new), 1, rel)
            # Only the pixels of an AGA dual-playfield line change: the OCS and ECS form of the rule is still there.
            text = (core / 'Components/Denise/Denise.cpp').read_text(encoding='utf-8')
            self.assertIn('state.zpf1 || isAGA() ? 0xFF : 0x00', text)
            self.assertIn('state.zpf2 || isAGA() ? 0xFF : 0x00', text)


if __name__ == '__main__':
    unittest.main()
