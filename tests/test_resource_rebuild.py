"""The build tracks the files a game's resources embed (retrorecomp/resource_rebuild.py): on the portable toolchain when it is
installed (CMake, Ninja, llvm-mingw), a tiny project's resources are rebuilt when an RCDATA file changes and when an icon of an
included .rc file changes, and nothing is rebuilt when nothing changed. Windows only (llvm-rc); the Linux .incbin side is the same
CMake and is witnessed in WSL. No ROM."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from retrorecomp import resource_rebuild

ROOT = Path(__file__).resolve().parents[1]


def tools():
    try:
        from retrorecomp import toolchain
        folder = toolchain.tools_directory()
    except Exception:
        return None
    cmake, ninja, llvm = folder / 'cmake/bin/cmake.exe', folder / 'ninja', folder / 'llvm-mingw/bin'
    return (cmake, ninja, llvm) if cmake.is_file() and (llvm / 'clang.exe').is_file() else None


class CmakeLinesTests(unittest.TestCase):
    def test_the_lines_name_both_embeddings(self):
        text = '\n'.join(resource_rebuild.CMAKE_LINES)
        self.assertIn('rr_embedded_depends(content.rc', text)
        self.assertIn('rr_embedded_depends(embedded_resources.S', text)
        self.assertIn('OBJECT_DEPENDS', text)
        self.assertIn('CMAKE_CONFIGURE_DEPENDS', text)

    def test_the_chain_builders_write_them(self):
        for module in ('zxs_build', 'sg1000_build', 'coleco_build', 'msx_build', 'cpc_build'):
            source = (ROOT / 'retrorecomp' / f'{module}.py').read_text(encoding='utf-8')
            self.assertIn('*resource_rebuild.CMAKE_LINES', source, module)
            self.assertNotIn(".touch()", source, module)

    @unittest.skipUnless(os.name == 'nt' and tools(), 'the portable toolchain (CMake, Ninja, llvm-mingw) is not installed')
    def test_a_changed_embedded_file_rebuilds_the_resources(self):
        cmake, ninja, llvm = tools()
        folder = Path(tempfile.mkdtemp(prefix='rr-resources-'))
        env = dict(os.environ, PATH=os.pathsep.join([str(llvm), str(ninja), os.environ.get('PATH', '')]))
        try:
            (folder / 'data.bin').write_bytes(b'one')
            (folder / 'game.ico').write_bytes(Path(ROOT / 'assets').rglob('*.ico').__next__().read_bytes())
            (folder / 'content.rc').write_text('101 RCDATA "data.bin"\n#include "game_resources.rc"\n', encoding='utf-8')
            (folder / 'game_resources.rc').write_text('1 ICON "game.ico"\n', encoding='utf-8')
            (folder / 'main.c').write_text('int main(void){return 0;}\n', encoding='utf-8')
            (folder / 'CMakeLists.txt').write_text('\n'.join(['cmake_minimum_required(VERSION 3.20)', 'project(rr C RC)',
                                                              'add_executable(game main.c content.rc)', *resource_rebuild.CMAKE_LINES]) + '\n',
                                                   encoding='utf-8')

            def run(*args):
                done = subprocess.run([str(cmake), *args], cwd=folder, env=env, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                return done.stdout

            run('-S', '.', '-B', 'b', '-G', 'Ninja', '-DCMAKE_C_COMPILER=clang', '-DCMAKE_RC_COMPILER=llvm-rc')
            run('--build', 'b')
            self.assertIn('no work to do', run('--build', 'b'))
            time.sleep(1.1)
            (folder / 'data.bin').write_bytes(b'two')
            self.assertIn('content.rc', run('--build', 'b'))
            self.assertIn(b'two', (folder / 'b' / 'game.exe').read_bytes())
            self.assertIn('no work to do', run('--build', 'b'))
            time.sleep(1.1)
            icon = bytearray((folder / 'game.ico').read_bytes())
            icon[-1] ^= 0xFF
            (folder / 'game.ico').write_bytes(bytes(icon))
            self.assertIn('content.rc', run('--build', 'b'))
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
