"""Every module that holds the schema 3 records of a machine exposes its ceilings in one form: `PATH_CAPS`, {name of a path kind: rows}.

The names are those of `entry_set` (what the base compares between players), so the site's base builder reads the ceilings of a machine without a name of
its own for each (`ROW_LIMIT` stays in the CPS-1 module for what still reads it).
"""
import unittest

from retrorecomp import cps1_knowledge, cps2_knowledge, knowledge, path_profiles as pp, x68_knowledge
from tests import test_cps1_knowledge as cps1_tests
from tests import test_x68_knowledge as x68_tests


class PathCapsTests(unittest.TestCase):
    def test_every_schema_3_module_has_path_caps_of_the_same_form(self):
        modules = {system: knowledge.schema3_module(system) for system in pp.SCHEMA3_ONLY}
        self.assertEqual(set(modules), {'cps1', 'cps2', 'x68'})
        for system, module in modules.items():
            with self.subTest(system):
                caps = module.PATH_CAPS
                self.assertIsInstance(caps, dict)
                self.assertTrue(caps)
                for name, cap in caps.items():
                    self.assertIsInstance(name, str)
                    self.assertIs(type(cap), int)
                    self.assertGreater(cap, 0)

    def test_the_module_of_a_machine_is_declared_by_its_profile(self):
        from retrorecomp.systems import ALL_PROFILES
        declared = {p.id: p.shared_knowledge.module for p in ALL_PROFILES if p.shared_knowledge and p.shared_knowledge.module}
        self.assertEqual(declared, {'cps1': 'cps1_knowledge', 'cps2': 'cps2_knowledge', 'x68': 'x68_knowledge'})
        self.assertEqual(set(declared), set(pp.SCHEMA3_ONLY))
        self.assertIs(knowledge.schema3_module('cps1'), cps1_knowledge)
        self.assertIs(knowledge.schema3_module('cps2'), cps2_knowledge)
        self.assertIs(knowledge.schema3_module('x68'), x68_knowledge)
        for system in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'zx'):
            self.assertIsNone(knowledge.schema3_module(system), system)

    def test_the_names_are_those_of_entry_set_and_the_values_the_profile_ceilings(self):
        cps1_names = {name for name, _ in cps1_knowledge.entry_set(cps1_tests.a_record())}
        x68_names = {name for name, _ in x68_knowledge.entry_set(x68_tests.a_record())}
        self.assertEqual(cps1_names, set(cps1_knowledge.PATH_CAPS))
        self.assertEqual(x68_names, set(x68_knowledge.PATH_CAPS))
        self.assertEqual(cps2_knowledge.PATH_CAPS, cps1_knowledge.PATH_CAPS)
        # The CPS-1 values are unchanged, and the X68000's are the caps its profile declares for the shapes of those kinds.
        self.assertEqual(cps1_knowledge.PATH_CAPS, {'m68k_ram': 4096, 'z80_ram': 4096})
        self.assertEqual(cps1_knowledge.ROW_LIMIT, 4096)
        profile = pp.PROFILES[('m68k', 'x68')]
        self.assertEqual(x68_knowledge.PATH_CAPS, {'x68_span': profile.caps['span'], 'x68_ipl': profile.caps['insn']})


if __name__ == '__main__':
    unittest.main()
