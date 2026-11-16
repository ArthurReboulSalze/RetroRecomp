"""native/psx_machine/psx_spirv_reflect.c against SPIRV-Cross (tools/psx_spirv_reflect_selftest.py): the layout our reflector reads
from each prebuilt shader of the pinned Beetle PSX is the one upstream's SPIRV-Cross reads. Runs when a C and C++ compiler and the
pinned Beetle checkout are there, and skips cleanly otherwise. SPIRV-Cross is the oracle of this check only: no game holds it."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('psx_spirv_reflect_selftest', ROOT / 'tools' / 'psx_spirv_reflect_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)
REFLECTOR = (ROOT / 'native/psx_machine/psx_spirv_reflect.c').read_text(encoding='utf-8')


class ReflectorTests(unittest.TestCase):
    def test_every_prebuilt_shader_has_the_layout_spirv_cross_reads(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        # A folder of the build tree (not a temporary one), so that a second run only relinks what changed.
        result = selftest.run_check(ROOT / '.build/psx-spirv-reflect-selftest')
        different = [(s['name'], s['first_difference']) for s in result['shaders'] if not s['equal']]
        self.assertEqual(different, [])
        self.assertGreaterEqual(result['prebuilt'], 90)
        # the check means something: most shaders declare bindings, push constants or specialization constants
        self.assertGreater(sum(1 for s in result['shaders'] if s['bindings']), 60)
        self.assertGreater(sum(1 for s in result['shaders'] if s['push_constant_bytes']), 50)
        self.assertGreater(sum(1 for s in result['shaders'] if s['spec_constants']), 20)

    def test_the_reflector_is_ours_and_holds_no_spirv_cross(self):
        self.assertIn('Retro-Recomp\'s own code, MIT', REFLECTOR)
        self.assertNotIn('spirv_cross', REFLECTOR)
        self.assertNotIn('#include <spirv', REFLECTOR)
        # the oracle is compiled under another name, from the pinned checkout, never from the repository
        project = selftest.cmake_project(ROOT / '.deps' / 'beetle-psx')
        self.assertIn('rhi_spirv_reflect=upstream_reflect', project)
        self.assertIn('rhi_spirv_reflect=ours_reflect', project)
        self.assertNotIn('SPIRV-Cross', '\n'.join(p.as_posix() for p in (ROOT / 'native').rglob('*') if p.is_dir()))


if __name__ == '__main__':
    unittest.main()
