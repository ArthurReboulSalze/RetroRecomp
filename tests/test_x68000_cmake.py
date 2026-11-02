"""native/x68000_reference/CMakeLists.txt names only files that exist (no private adapter of the removed libretro comparison base)."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'native' / 'x68000_reference'
TEXT = (DIRECTORY / 'CMakeLists.txt').read_text(encoding='utf-8')
VARIABLES = {'${CMAKE_CURRENT_SOURCE_DIR}': DIRECTORY, '${RR_GLUE_DIR}': ROOT / 'native' / 'x68000_machine',
             '${RR_COMMON_NATIVE}': ROOT / 'native'}


def resolve(token):
    for name, base in VARIABLES.items():
        if token.startswith(name):
            return base / token[len(name):].lstrip('/')
    return None


class ReferenceBuildTests(unittest.TestCase):
    def test_no_file_of_the_removed_libretro_comparison_base_is_named(self):
        for name in ('x68000_hardware.py', 'x68000_session_hardware.py', 'x68000_disk_hardware.py', 'adapt_upstream.cmake',
                     'PX68K_DIR', 'HARDWARE_FIXES', 'session_bridge.c', 'media_probe.c', 'libretro/joystick.c', 'libretro/state.c'):
            self.assertNotIn(name, TEXT, name)

    def test_only_the_hissorii_base_is_accepted(self):
        self.assertIn('set_property(CACHE RR_X68000_MACHINE_BASE PROPERTY STRINGS hissorii)', TEXT)
        self.assertRegex(TEXT, r'if\(NOT RR_X68000_MACHINE_BASE STREQUAL "hissorii"\)\s+message\(FATAL_ERROR')

    def test_every_generator_it_hashes_is_a_file_of_tools(self):
        names = re.findall(r'rr_tool_hash\(\w+ ([\w.]+)\)', TEXT)
        self.assertEqual(sorted(set(names)), ['x68000_base74.py', 'x68000_state_hardware.py'])
        for name in names:
            self.assertTrue((ROOT / 'tools' / name).is_file(), name)

    def test_every_path_it_builds_from_a_known_folder_exists(self):
        tokens = set(re.findall(r'"?(\$\{(?:CMAKE_CURRENT_SOURCE_DIR|RR_GLUE_DIR|RR_COMMON_NATIVE)\}/[^"\s)]+)', TEXT))
        files = {resolve(token) for token in tokens if '${' not in token[token.index('}') + 1:]}
        self.assertGreater(len(files), 15)
        missing = sorted(str(path.relative_to(ROOT)) for path in files if path and not path.exists())
        self.assertEqual(missing, [])

    def test_the_helper_and_state_file_lists_name_files_beside_the_cmake_file(self):
        for variable in ('RR_REFERENCE_HELPERS', 'RR_STATE_FILES'):
            body = re.search(r'(?:set|list)\((?:APPEND )?' + variable + r'\s+(.*?)\)\n', TEXT, re.S).group(1)
            for token in re.findall(r'[\w./${}-]+\.(?:c|h)\b', body):
                path = resolve(token) if token.startswith('${') else DIRECTORY / token
                if '${' in token and path is None:
                    continue
                self.assertTrue(path.is_file(), (variable, token))


if __name__ == '__main__':
    unittest.main()
