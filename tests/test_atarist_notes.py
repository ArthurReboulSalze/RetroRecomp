"""The Atari ST's table of known route stops: keyed by a dump's SHA-256, words about a game and never its bytes, merged into the report's route_warnings."""
import re
import unittest

from retrorecomp import atarist_notes


class RouteStopsTests(unittest.TestCase):
    def test_every_key_is_a_sha256_and_every_note_a_sentence_that_names_its_game(self):
        for identity, note in atarist_notes.ROUTE_STOPS.items():
            self.assertRegex(identity, r'^[0-9a-f]{64}$')
            self.assertRegex(note, r'^[A-Z][\w\' -]+: .{40,}')
            self.assertFalse(re.search(r'[^\x20-\x7e]', note), note)   # plain text: it goes in a report and in documents

    def test_a_dump_in_the_table_gets_its_words_and_any_other_nothing(self):
        identity = next(iter(atarist_notes.ROUTE_STOPS))
        words = atarist_notes.route_stops(identity)
        self.assertEqual(len(words), 1)
        self.assertTrue(words[0].startswith('known stop (panel of 13 November 2026): '))
        self.assertEqual(atarist_notes.route_stops('0' * 64), [])
        self.assertEqual(atarist_notes.route_stops(''), [])

    def test_no_note_claims_an_answer_or_a_bypass(self):
        for note in atarist_notes.ROUTE_STOPS.values():
            self.assertNotRegex(note.lower(), r'\b(patch|crack|bypass|skip)ed\b|\bis the answer\b')


if __name__ == '__main__':
    unittest.main()
