import os
from pathlib import Path
import tempfile
import unittest

from retrorecomp.gameboy_build import compact_dispatch, preserve_unchanged_sources, share_native_bodies, safe_body_entries
from retrorecomp.gameboy_boundary import repair_bank_boundaries, repair_empty_bodies
from unittest.mock import patch


class GameBoyBuildTests(unittest.TestCase):
    def test_large_incremental_sources_are_hashed_without_loading_whole_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'game.c';source.write_bytes(b'// generated\n'*100000)
            stamp=1_600_000_000_000_000_000;os.utime(source,ns=(stamp,stamp))
            with patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded source read')):
                with preserve_unchanged_sources(root):
                    with source.open('ab') as stream:stream.write(b'// changed\n')
            self.assertNotEqual(source.stat().st_mtime_ns,stamp)
            os.utime(source,ns=(stamp,stamp))
            with patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded source read')):
                with preserve_unchanged_sources(root):os.utime(source,None)
            self.assertEqual(source.stat().st_mtime_ns,stamp)

    def test_incremental_sources_preserve_only_exact_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unchanged = root / 'game.c'
            changed = root / 'game_internal.h'
            unchanged.write_text('original')
            changed.write_text('original')
            stamp = 1_600_000_000_000_000_000
            for path in (unchanged, changed):
                os.utime(path, ns=(stamp, stamp))
            with preserve_unchanged_sources(root):
                unchanged.write_text('original')
                changed.write_text('modified')
            self.assertEqual(unchanged.stat().st_mtime_ns, stamp)
            self.assertNotEqual(changed.stat().st_mtime_ns, stamp)

    def test_unrecognized_dispatch_page_is_not_rewritten(self):
        source = 'void game_dispatch_00(GBContext* ctx, uint16_t addr, uint16_t bank) {\n    custom(ctx);\n}'
        self.assertEqual(compact_dispatch(source), (source, 0))

    def test_only_pure_wrappers_are_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('game_internal.h', 'game.c', 'game_main.c'):
                (root / name).write_text('void func_0100(GBContext* ctx);\n')
            path = root / 'game_funcs_0.c'
            path.write_text('static void body_0100(GBContext* ctx) {\n    ctx->pc++;\n}\n'
                            'void func_0100(GBContext* ctx) {\n    body_0100(ctx);\n}\n'
                            'void func_0200(GBContext* ctx) {\n    hook(ctx);\n    body_0100(ctx);\n}\n')
            result = share_native_bodies(root)
            self.assertEqual(result['wrappers_removed'], 1)
            self.assertIn('void func_0200', path.read_text())
            self.assertIn('hook(ctx);', path.read_text())
            self.assertNotIn('void func_0100', path.read_text())

    def test_multi_entry_body_preserves_every_destination_and_default(self):
        source = ('static void body_1000(GBContext* ctx) {\n'
                  '    gbrt_note_generated_direct_transition(ctx);\n'
                  '    switch (ctx->pc) {\n'
                  '        case 0x1000: goto loc_1000;\n'
                  '        case 0x1200: goto loc_1200;\n'
                  '        default: break;\n    }\n'
                  'loc_1000:\n    first(ctx);\nloc_1200:\n    second(ctx);\n}\n')
        rewritten, count = safe_body_entries(source)
        self.assertEqual(count, 1)
        self.assertIn('if (ctx->pc == 0x1000) goto loc_1000;', rewritten)
        self.assertIn('if (ctx->pc == 0x1200) goto loc_1200;', rewritten)
        self.assertEqual(rewritten[rewritten.index('loc_1000:\n'):],
                         source[source.index('loc_1000:\n'):])
        self.assertEqual(safe_body_entries(source.replace('default: break;', 'default: custom(ctx);')),
                         (source.replace('default: break;', 'default: custom(ctx);'), 0))

    def test_live_boundary_does_not_remove_adjacent_instruction(self):
        rom = bytearray(0x8000)
        rom[0x3FFF] = 0xF0
        source = ('static void body_3ffe(GBContext* ctx) {\n'
                  'loc_3ffe:\n    /* 3ffe */ ctx->b++;\n'
                  'loc_3fff:\n    /* 3fff */ ctx->a = gb_read8(ctx, 0xffc3);\n    return;\n}\n')
        output, native, fallback = repair_bank_boundaries(source, rom)
        self.assertEqual((native, fallback), (1, 0))
        self.assertIn('ctx->b++;', output)
        self.assertIn('gb_read8(ctx, 0x4000)', output)
        self.assertNotIn('0xffc3', output)
        self.assertTrue(output.endswith('}\n'))

    def test_bank_identity_and_unsupported_prefix_fail_safely(self):
        rom = bytearray(0xC000)
        rom[0xBFFF] = 0xCB
        source = 'static void body_02_7fff(GBContext* ctx) {\nloc_02_7fff:\n    /* 02:7fff */ wrong_constant(ctx);\n}\n'
        output, native, fallback = repair_bank_boundaries(source, rom)
        self.assertEqual((native, fallback), (0, 1))
        self.assertNotIn('wrong_constant', output)
        self.assertIn('gbrt_execute_dispatch_fallback', output)

    def test_empty_bodies_become_rst_38_or_the_interpreter(self):
        rom = bytearray(0x10000)
        rom[0x8000 + 0x0fe8] = 0xFF     # bank 2, 0x4fe8: padding
        rom[0x8000 + 0x0123] = 0xD3     # bank 2, 0x4123: undefined opcode
        rom[0x0150] = 0xFF               # bank 0, 0x0150
        empty = ('/* Shared body at {where} */\nstatic void body_{name}(GBContext* ctx) {{\n'
                 '    gbrt_note_generated_direct_transition(ctx);\n{switch}loc_{name}:\n'
                 '    /* warning: fallthrough to unanalyzed code at 0x4fe6 in bank 2 */\n    return;\n}}\n\n')
        source = (empty.format(where='02:4fe8', name='02_4fe8', switch='') +
                  empty.format(where='02:4123', name='02_4123', switch='') +
                  empty.format(where='0150', name='0150', switch='') +
                  empty.format(where='02:4fe9', name='02_4fe9', switch=
                      '    switch (ctx->pc) {\n        case 0x4fe9: goto loc_02_4fe9;\n'
                      '        case 0x4fea: goto pc_4fea;\n        default: break;\n    }\n\n') +
                  '/* Shared body at 0200 */\nstatic void body_0200(GBContext* ctx) {\n'
                  '    gbrt_note_generated_direct_transition(ctx);\nloc_0200:\n'
                  '    /* 0200 */     ctx->a = 1;\n    return;\n}\n')
        output, rst, interpreted = repair_empty_bodies(source, rom)
        self.assertEqual((rst, interpreted), (2, 2))
        self.assertIn('ctx->pc = 0x4fe8;\n    gbrt_timed_rst(ctx, 0x38, 0x4fe9);', output)
        self.assertIn('ctx->pc = 0x0150;\n    gbrt_timed_rst(ctx, 0x38, 0x151);', output)
        self.assertIn('ctx->pc = 0x4123;\n    gbrt_execute_dispatch_fallback(', output)
        # Several entries: the caller's pc is kept, and no goto is left dangling.
        self.assertNotIn('goto pc_4fea', output)
        self.assertIn('ctx->a = 1;', output)
        self.assertEqual(output.count('\n}\n'), 5)
        self.assertEqual(repair_empty_bodies(output, rom), (output, 0, 0))


if __name__ == '__main__':
    unittest.main()
