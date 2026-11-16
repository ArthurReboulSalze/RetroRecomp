"""Every CMake build the converter runs names its configuration.

With Visual Studio (the fallback toolchain, a multi-configuration generator) a build without `--config Release` is a
Debug build in `Debug/`, while `platforms.build_executable` looks in `Release/`: the conversion stops with « … was not
built » (GitHub issue 1, the Game Boy Advance, 16 November 2026). The portable tools (Ninja) ignore the option, so only
a player with Visual Studio sees the fault: this scan keeps every machine honest."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_CALL = re.compile(r"""\[\s*cmake\s*,\s*['"]--build['"]""")


class BuildConfigurationTests(unittest.TestCase):
    def test_every_cmake_build_names_the_release_configuration(self):
        missing, seen = [], 0
        for path in sorted((ROOT / 'retrorecomp').glob('*.py')):
            text = path.read_text(encoding='utf-8')
            for match in BUILD_CALL.finditer(text):
                seen += 1
                end = text.find(']', match.end())
                call = text[match.start():end]
                if not re.search(r"""['"]--config['"]\s*,\s*['"]Release['"]""", call):
                    line = text.count('\n', 0, match.start()) + 1
                    missing.append(f'{path.name}:{line}')
        self.assertGreater(seen, 20, 'the scan found the build calls')
        self.assertEqual(missing, [], 'cmake --build without --config Release (a Debug build under Visual Studio)')


if __name__ == '__main__':
    unittest.main()
