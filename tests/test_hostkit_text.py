"""The adapters' own texts in the five game languages (native/hostkit/adapters/rrhk_text.h): every RrhkText row of every adapter has
five strings, none empty, all printable ASCII, as the games' menus write them (the generated games embed the Latin font subsets only).
Reads the sources: no compiler, no ROM."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / 'native' / 'hostkit' / 'adapters'
DECLARATION = re.compile(r'\bRrhkText\s+\w+\s*(?:\[[^\]]*\]\s*)*=\s*\{')
LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def _comments_out(text: str) -> str:
    text = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


def _initialiser(text: str, start: int) -> str:
    """The braces opened at text[start] ('{') with what they hold, strings skipped as a whole."""
    depth, n = 0, start
    while n < len(text):
        if text[n] == '"':
            n = LITERAL.match(text, n).end()
            continue
        depth += {'{': 1, '}': -1}.get(text[n], 0)
        n += 1
        if depth == 0:
            return text[start:n]
    raise AssertionError('unclosed initialiser')


def rows(text: str):
    """Each row's strings (adjacent literals joined, as C joins them), per RrhkText declaration of a source."""
    text = _comments_out(text)
    for match in DECLARATION.finditer(text):
        body = _initialiser(text, match.end() - 1)
        inner = body[1:-1]
        groups = re.findall(r'\{([^{}]*)\}', inner) if '{' in inner else [inner]
        for group in groups:
            strings = []
            for item in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', group):
                parts = LITERAL.findall(item)
                if item.strip():
                    strings.append(''.join(parts) if parts else None)
            yield match.group(0), strings


class AdapterTextTests(unittest.TestCase):
    def test_every_row_has_five_ascii_texts(self):
        found = 0
        for path in sorted(ADAPTERS.iterdir()):
            if path.suffix not in ('.inc', '.c', '.h') or path.name == 'rrhk_text.h':
                continue
            for declaration, strings in rows(path.read_text(encoding='utf-8')):
                found += 1
                where = f'{path.name}: {declaration}'
                self.assertEqual(len(strings), 5, where)                    # en, fr, it, es, de
                for text in strings:
                    self.assertTrue(text, f'{where} {strings}')               # a literal, not empty (the fallback is for nobody's rows)
                    self.assertTrue(all(' ' <= ch <= '~' for ch in text), f'{where} {text!r}')
        self.assertGreaterEqual(found, 2)                                       # the on-screen keypad's title and hint at least

    def test_the_reader_sees_a_bad_row(self):
        # A positive control: the reader catches a short row, an accent and an array of rows.
        bad = ('static const RrhkText a = {"One", "Un", "Uno", "Uno"};\n'
               'static const RrhkText b[2] = {{"a", "b", "c", "d", "e"}, {"Sound", "Son é", "x", "y" "z", "w"}};\n')
        found = list(rows(bad))
        self.assertEqual([len(strings) for _, strings in found], [4, 5, 5])
        self.assertEqual(found[2][1][1], 'Son é')
        self.assertEqual(found[2][1][3], 'yz')


if __name__ == '__main__':
    unittest.main()
