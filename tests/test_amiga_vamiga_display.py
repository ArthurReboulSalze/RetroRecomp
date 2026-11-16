import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import amiga_conversion, amiga_knowledge, amiga_vamiga, amiga_vamiga_display

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps' / 'vamiga' / 'Core'


def spans(text, headers):
    """(start, stop) of each listed function in `text`: its header back to the comment lines and the return type above it, on to the next
    line that closes a block at the left margin (a class: to its `};`)."""
    out = []
    for header in headers:
        for at in (n for n in range(len(text)) if text.startswith(header, n)):
            out.append(_span(text, header, at))
    return out


def _span(text, header, at):
    if True:
        start = text.rfind('\n', 0, at) + 1
        while True:
            previous = text.rfind('\n', 0, start - 1) + 1
            line = text[previous:start].strip()
            if start and (line.startswith('//') or line in ('', 'void', 'bool', 'u32', 'isize') or line.startswith('template')):
                start = previous
            else:
                break
        stop = text.find('\n};\n' if header.startswith('class ') else '\n}\n', at)
        return start, stop if stop >= 0 else len(text)


class PictureChangesTests(unittest.TestCase):
    # The line between a display change and a generator source: `amiga_vamiga_display` is not pinned (a path cannot notice which colour a
    # pixel gets, nor a display shortcut the self-test replays against vAmiga's path), so it may only change the files and functions of
    # DISPLAY_FUNCTIONS, Denise and the bitplane and sprite slots of Agnus, never the CPU, the memory, the CIAs, Paula, the Copper or the Blitter.
    def test_the_module_is_outside_the_generator_pins_and_touches_the_display_only(self):
        self.assertNotIn('retrorecomp/amiga_vamiga_display.py', amiga_knowledge.GENERATOR_SOURCES)
        self.assertIn('retrorecomp/amiga_vamiga.py', amiga_knowledge.GENERATOR_SOURCES)
        self.assertTrue(amiga_vamiga_display.REPLACEMENTS)
        for rel, old, new in amiga_vamiga_display.REPLACEMENTS:
            self.assertIn(rel, amiga_vamiga_display.DISPLAY_FUNCTIONS, rel)
            self.assertTrue(rel.startswith(('Components/Denise/', 'Components/Agnus/Agnus')), rel)
            self.assertNotEqual(old, new)
        for rel in amiga_vamiga_display.DISPLAY_FUNCTIONS:
            self.assertFalse(any(part in rel for part in ('CPU', 'Moira', 'Memory', 'Paula', 'CIA', 'Copper', 'Blitter')), rel)

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
                # The replacement lies within one listed function: from the comment block just above its return type to its closing brace.
                end = at + len(new)
                inside = [(start, stop) for start, stop in spans(text, amiga_vamiga_display.DISPLAY_FUNCTIONS[rel]) if start <= at and end <= stop]
                self.assertTrue(inside, f'{rel}: a replacement outside the listed functions')
                # The function says the change is ours (MPL-2.0 text), unless it is one of our own functions (rr...), ours whole.
                start, stop = inside[0]
                self.assertTrue('Retro-Recomp modification (MPL-2.0, like this file)' in text[start:stop] or '::rr' in text[start:stop], rel)
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
