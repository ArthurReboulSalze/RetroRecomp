"""The X68000 host prepares its private game data in a folder deeper than 260 characters (Windows long paths).

The real native/x68000_reference/payload.c is compiled against stub resources (a few authored bytes, no disk image,
no firmware, no ROM) and run on a folder tree created under the worktree's .build, which this test deletes.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = '0123456789abcdef' * 4

# What x68000_conversion.payload() declares: the same record type and the same fields, with authored bytes.
PAYLOAD_HEADER = '''#ifndef RR_X68000_PAYLOAD_CONFIG
#define RR_X68000_PAYLOAD_CONFIG
#define RR_X68K_SOURCE_IDENTITY "%s"
typedef struct {const char *path;unsigned resource;int writable;} RrX68kPayloadFile;
static const RrX68kPayloadFile rr_x68k_files[]={
{"media/disk-01.d88",300,1},
{"media/game.m3u",301,0},
{"system/keropi/iplrom.dat",302,0},
};
#define RR_X68K_FILE_COUNT (sizeof(rr_x68k_files)/sizeof(rr_x68k_files[0]))
#endif
''' % IDENTITY

# The real embedded_resources.h needs SDL and the executable's resources; the payload only calls rr_resource().
RESOURCES_HEADER = '''#ifndef RR_EMBEDDED_RESOURCES_H
#define RR_EMBEDDED_RESOURCES_H
#include <stddef.h>
static inline const void *rr_resource(unsigned id,size_t *size) {
    static const unsigned char disk[]="authored disk bytes";
    static const unsigned char list[]="disk-01.d88\\n";
    static const unsigned char ipl[]="authored ipl bytes";
    switch(id){
    case 300:*size=sizeof(disk)-1;return disk;
    case 301:*size=sizeof(list)-1;return list;
    case 302:*size=sizeof(ipl)-1;return ipl;
    }
    *size=0;return NULL;
}
#endif
'''

CONTENT = {'media/disk-01.d88': b'authored disk bytes', 'media/game.m3u': b'disk-01.d88\n',
           'system/keropi/iplrom.dat': b'authored ipl bytes'}


def extended(path):
    """What Python needs to reach a path beyond 260 characters on Windows."""
    path = os.path.abspath(path)
    return '\\\\?\\' + path if os.name == 'nt' and not path.startswith('\\\\?\\') else path


class LongPathPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from retrorecomp.core import toolchain
        from retrorecomp.platforms import build_executable, cmake_target_args
        cls.build_temp = tempfile.TemporaryDirectory(prefix='rr-x68000-payload-')
        project = Path(cls.build_temp.name)
        stubs = project / 'stubs'
        stubs.mkdir()
        (stubs / 'x68000_payload.h').write_text(PAYLOAD_HEADER, encoding='ascii', newline='\n')
        (stubs / 'embedded_resources.h').write_text(RESOURCES_HEADER, encoding='ascii', newline='\n')
        source = (ROOT / 'native/x68000_reference').as_posix()
        (project / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.20)\n'
            'project(PayloadFixtures LANGUAGES C)\n'
            'set(CMAKE_C_STANDARD 11)\n'
            f'add_executable(payload-test "{ROOT.as_posix()}/tests/x68000_payload_harness.c" "{source}/payload.c")\n'
            # The stubs come first: the real embedded_resources.h in native/ needs SDL.
            f'target_include_directories(payload-test PRIVATE "{stubs.as_posix()}" "{source}" "{ROOT.as_posix()}/native")\n'
            'if(MSVC)\n'
            'target_compile_options(payload-test PRIVATE /W4 /WX /utf-8)\n'
            'target_compile_definitions(payload-test PRIVATE _CRT_SECURE_NO_WARNINGS)\n'
            'else()\n'
            'target_compile_options(payload-test PRIVATE -Wall -Wextra -Werror)\n'
            'endif()\n', encoding='utf-8')
        cmake, generator = toolchain()
        for command in (
            [str(cmake), '-S', str(project), '-B', str(project / 'build'), '-G', generator, *cmake_target_args()],
            [str(cmake), '--build', str(project / 'build'), '--config', 'Release'],
        ):
            compiled = subprocess.run(command, capture_output=True, text=True)
            if compiled.returncode:
                cls.build_temp.cleanup()
                raise RuntimeError(compiled.stdout + compiled.stderr)
        cls.binary = build_executable(project / 'build', 'payload-test')

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def setUp(self):
        scratch = ROOT / '.build'
        scratch.mkdir(exist_ok=True)
        self.tree = scratch / f'x68000-payload-long-{os.getpid()}'
        self.addCleanup(lambda: shutil.rmtree(extended(self.tree), ignore_errors=True))

    def folder(self, depth):
        """A base folder of `depth` levels of 40 characters under the scratch tree, as the host receives it."""
        base = self.tree
        for level in range(depth):
            base = base / (f'level-{level:02}-' + 'x' * 30)
        os.makedirs(extended(base))
        return str(base) + os.sep

    def prepare(self, base):
        result = subprocess.run([str(self.binary), base], capture_output=True, text=True)
        return result.returncode, result.stdout.strip()

    def game_folder(self, base):
        return Path(base) / 'datas' / 'games' / ('x68-' + IDENTITY)

    def test_a_folder_deeper_than_260_characters_is_prepared_without_changing_the_returned_path(self):
        base = self.folder(8)
        game = self.game_folder(base)
        self.assertGreater(len(str(game / 'media' / 'disk-01.d88.new')), 300)
        status, output = self.prepare(base)
        self.assertEqual((status, output), (0, 'DIRECTORY ' + str(game)))
        for name, content in CONTENT.items():
            with open(extended(game / name), 'rb') as handle:
                self.assertEqual(handle.read(), content, name)
        self.assertEqual(sorted(os.listdir(extended(game / 'media'))), ['disk-01.d88', 'game.m3u'])
        self.assertTrue(os.path.isfile(extended(game / 'session.lock')))
        # A second start finds the same files, keeps a writable disk the player changed and refuses a changed host file.
        with open(extended(game / 'media/disk-01.d88'), 'wb') as handle:
            handle.write(b'the player wrote here')
        self.assertEqual(self.prepare(base)[0], 0)
        with open(extended(game / 'media/disk-01.d88'), 'rb') as handle:
            self.assertEqual(handle.read(), b'the player wrote here')
        with open(extended(game / 'media/game.m3u'), 'wb') as handle:
            handle.write(b'changed')
        self.assertEqual(self.prepare(base), (1, 'PREPARE-FAILED'))

    def test_the_forward_slash_spelling_of_a_long_folder_works_too(self):
        base = self.folder(8)
        status, output = self.prepare(base.replace(os.sep, '/'))
        self.assertEqual(status, 0, output)
        with open(extended(self.game_folder(base) / 'system/keropi/iplrom.dat'), 'rb') as handle:
            self.assertEqual(handle.read(), CONTENT['system/keropi/iplrom.dat'])

    def test_a_short_folder_is_prepared_as_before(self):
        base = self.folder(0)
        game = self.game_folder(base)
        self.assertLess(len(str(game / 'media' / 'disk-01.d88.new')), 240)
        status, output = self.prepare(base)
        self.assertEqual((status, output), (0, 'DIRECTORY ' + str(game)))
        self.assertEqual(sorted(os.listdir(game / 'media')), ['disk-01.d88', 'game.m3u'])


if __name__ == '__main__':
    unittest.main()
