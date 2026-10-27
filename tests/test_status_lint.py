"""Status-lint checks on synthetic fixtures; the real repo result is printed only."""
import io
import unittest
from contextlib import redirect_stdout

from tools.status_lint import main, readme_section, sentence_status


CONSISTENT_README = """# Demo
## Console support

| Console | Current status |
| --- | --- |
| Master System | Supported; two players |
| Super Nintendo | Supported standard cartridges |
| Capcom CPS-1 | Experimental; arcade boards |
"""

CONTRADICTING_README = """# Demo
## Console support

| Console | Current status |
| --- | --- |
| Capcom CPS-1 | Supported; arcade boards |
"""


class SentenceStatusTests(unittest.TestCase):
    def test_plain_status_words(self):
        self.assertEqual(sentence_status("Master System is supported."), "supported")
        self.assertEqual(sentence_status("Mega Drive supports standard cartridges."), "supported")
        self.assertEqual(sentence_status("The experimental NES profile."), "experimental")

    def test_negated_experimental_reads_as_supported(self):
        self.assertEqual(
            sentence_status("The Super Nintendo standard profile is no longer "
                            "experimental: LoROM/HiROM."), "supported")
        self.assertEqual(
            sentence_status("Super Nintendo leaves experimental status."), "supported")

    def test_unsupported_word_states_nothing(self):
        self.assertIsNone(
            sentence_status("Game Boy Color-only cartridges remain unsupported."))


class SyntheticLintTests(unittest.TestCase):
    # Attributes for every console the fixture README mentions: a console
    # missing from the map means "attribute absent", never "ignore".
    ATTRS = {"sms": None, "gg": None, "gb": None, "nes": None, "md": None,
             "snes": False, "ng": False, "cps1": True, "x68": True}

    def lint(self, attrs, readme, compat="", release="", pairs=()):
        from tools.status_lint import lint_data
        merged = dict(self.ATTRS)
        merged.update(attrs)
        return lint_data(merged, readme, compat, release, list(pairs))

    def test_consistent_statuses_pass(self):
        result = self.lint({"sms": None, "snes": False, "cps1": True},
                           CONSISTENT_README,
                           compat="Master System supports standard cartridges.",
                           pairs=[("en", "options_cps1_note",
                                   "Experimental Capcom CPS-1 profile.")])
        self.assertEqual(result.contradictions, [])
        rows = {row["id"]: row for row in result.rows}
        self.assertEqual(rows["sms"]["profile"], "absent -> supported?")
        self.assertEqual(rows["sms"]["readme"], "supported")
        self.assertEqual(rows["snes"]["profile"], "supported")
        self.assertEqual(rows["cps1"]["profile"], "experimental")
        self.assertEqual(rows["cps1"]["readme"], "experimental")
        self.assertEqual(rows["cps1"]["interface"], "experimental")
        self.assertEqual(rows["ng"]["release_notes"], "-")

    def test_readme_contradiction_is_reported(self):
        result = self.lint({"cps1": True}, CONTRADICTING_README)
        self.assertEqual(len(result.contradictions), 1)
        self.assertIn("Capcom CPS-1", result.contradictions[0])
        self.assertIn("'supported'", result.contradictions[0])

    def test_document_contradiction_for_absent_attribute(self):
        result = self.lint({"sms": None}, CONSISTENT_README,
                           compat="The experimental Master System profile accepts "
                                  "PAL cartridges.")
        self.assertEqual(len(result.contradictions), 1)
        self.assertIn("Master System", result.contradictions[0])

    def test_interface_contradiction_for_supported_profile(self):
        result = self.lint({"ng": False}, CONSISTENT_README,
                           pairs=[("en", "note", "Experimental Neo Geo mode is an option.")])
        self.assertEqual(len(result.contradictions), 1)
        self.assertIn("Neo Geo", result.contradictions[0])

    def test_localised_experimental_keyword_is_detected(self):
        result = self.lint({"x68": False}, CONSISTENT_README,
                           pairs=[("de", "options_x68_note",
                                   "Experimentelles Profil: DIM/XDF und X68000.")])
        self.assertEqual(len(result.contradictions), 1)

    def test_mixed_string_only_flags_consoles_named_in_the_experimental_sentence(self):
        pairs = [("en", "knowledge_scope",
                  "Shared consoles: Master System and Neo Geo. The experimental "
                  "CPS-1 and X68000 are not shared.")]
        result = self.lint({}, CONSISTENT_README, pairs=pairs)
        rows = {row["id"]: row for row in result.rows}
        self.assertEqual(rows["sms"]["interface"], "-")
        self.assertEqual(rows["ng"]["interface"], "-")
        self.assertEqual(rows["cps1"]["interface"], "experimental")
        self.assertEqual(rows["x68"]["interface"], "experimental")
        self.assertEqual(result.contradictions, [])

    def test_readme_section_extracted_until_next_heading(self):
        text = CONSISTENT_README + "\n## Other\n| Capcom CPS-1 | Supported |\n"
        section = readme_section(text)
        self.assertIn("Master System", section)
        self.assertNotIn("Other", section)


class RealRepositoryTests(unittest.TestCase):
    def test_real_repository_report_printed(self):
        """Runs the lint on this checkout and prints the result; no assertion."""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main([])
        print(buffer.getvalue(), end="")


if __name__ == "__main__":
    unittest.main()
