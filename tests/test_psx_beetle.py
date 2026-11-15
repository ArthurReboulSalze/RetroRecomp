"""What a PlayStation game compiles of Beetle PSX (retrorecomp/psx_beetle.py): the Vulkan renderer is in (1.7.7), and nothing a
GPL-2.0-only game cannot hold comes with it. No checkout, no compiler: the lists themselves."""
import unittest

from retrorecomp import psx_beetle as beetle
from retrorecomp.paths import ASSETS


class BeetleListsTests(unittest.TestCase):
    def test_the_vulkan_renderer_is_compiled_and_the_opengl_one_is_not(self):
        for rel in ('rhi/rhi_lib_vulkan.c', 'rhi/rhi_upscaler.c', 'rhi/rhi_tt.c'):
            self.assertIn(rel, beetle.SOURCES)
        self.assertNotIn('rhi/rhi_lib_gl.c', beetle.SOURCES)
        for define in ('HAVE_VULKAN', 'HAVE_HW'):
            self.assertIn(define, beetle.DEFINES)
        self.assertFalse([d for d in beetle.DEFINES if d.startswith(('HAVE_OPENGL', 'HAVE_GLSM'))])

    def test_nothing_under_apache_terms_alone_and_no_hdr_tables(self):
        # SPIRV-Cross and Beetle's own copy of the Vulkan headers (both Apache-2.0) live in parallel-psx, never copied
        self.assertNotIn('parallel-psx', beetle.FOLDERS)
        self.assertFalse([rel for rel in beetle.SOURCES if rel.startswith('parallel-psx') or rel.endswith('.cpp')])
        for rel in ('rhi/rhi_spirv_reflect.cpp', 'rhi/hdr_transform.c', 'rhi/hdr_aces2.c', 'rhi/hdr_filmic_contrast.h',
                    'rhi/hdr_filmic_desat.h'):
            self.assertIn(rel, beetle.EXCLUDED)
            self.assertNotIn(rel, beetle.SOURCES)
        # our replacements, compiled with the machine
        self.assertEqual(beetle.OWN_SOURCES, ('psx_spirv_reflect.c', 'psx_hdr_none.c'))
        for name in beetle.OWN_SOURCES:
            text = (ASSETS / 'native' / 'psx_machine' / name).read_text(encoding='utf-8')
            self.assertIn("Retro-Recomp's own code, MIT", text)

    def test_the_vulkan_headers_are_khronos_own_and_pinned(self):
        self.assertEqual(beetle.VULKAN_HEADERS_REPOSITORY, 'https://github.com/KhronosGroup/Vulkan-Headers.git')
        self.assertRegex(beetle.VULKAN_HEADERS_REV, r'^[0-9a-f]{40}$')
        self.assertIn('khronos/include', beetle.INCLUDES)
        self.assertNotIn('parallel-psx/khronos/include', beetle.INCLUDES)
        self.assertEqual(set(h for h in beetle.VULKAN_HEADERS if h.endswith('.h')),
                         {'include/vulkan/vulkan.h', 'include/vulkan/vulkan_core.h', 'include/vulkan/vk_platform.h'})

    def test_the_adaptation_digest_follows_our_files_and_the_headers(self):
        digest = beetle.adaptation_digest()
        self.assertRegex(digest, r'^[0-9a-f]{64}$')
        saved = beetle.VULKAN_HEADERS_REV
        try:
            beetle.VULKAN_HEADERS_REV = '0' * 40
            self.assertNotEqual(beetle.adaptation_digest(), digest)
        finally:
            beetle.VULKAN_HEADERS_REV = saved
        self.assertEqual(beetle.adaptation_digest(), digest)


class SessionOptionNamesTests(unittest.TestCase):
    SESSION = (ASSETS / 'native' / 'psx_machine' / 'psx_session.c').read_text(encoding='utf-8')

    def test_the_hardware_build_names_are_answered_under_the_session_names(self):
        # with HAVE_HW the core asks beetle_psx_hw_<name>: the session answers it as beetle_psx_<name>
        self.assertIn('!strncmp(key, "beetle_psx_hw_", 14)', self.SESSION)
        self.assertIn('snprintf(plain, sizeof plain, "beetle_psx_%s", key + 14);', self.SESSION)

    def test_the_software_renderer_draws(self):
        self.assertIn('{"beetle_psx_renderer", "software"},', self.SESSION)


if __name__ == '__main__':
    unittest.main()
