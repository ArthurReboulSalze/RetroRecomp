import json
import hashlib
from pathlib import Path
import re
import string
import tempfile
import unittest

from smsrecomp.i18n import STRINGS, catalog, tr
from smsrecomp.languages import LANGUAGES, LANGUAGE_NAMES, language_code, language_name
from smsrecomp.paths import ASSETS, save_game_language


class LanguageTests(unittest.TestCase):
    def test_all_ui_catalogues_are_complete_and_format_compatible(self):
        fields=lambda text:[field for _,field,_,_ in string.Formatter().parse(text) if field is not None]
        for code in LANGUAGES[2:]:
            values=catalog(code)['ui']
            self.assertEqual(set(values),set(STRINGS),code)
            for key,(english,_) in STRINGS.items():
                self.assertTrue(values[key],(code,key))
                self.assertEqual(sorted(fields(english)),sorted(fields(values[key])),(code,key))
                self.assertEqual(tr(key,code),values[key]) if not fields(english) else None

    def test_stable_codes_and_persistent_shared_setting(self):
        self.assertEqual(len(LANGUAGES),8)
        self.assertEqual(language_code('ja-JP'),'ja')
        self.assertEqual(language_code('zh_CN'),'zh')
        self.assertEqual(language_code('invalid'),'en')
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            for code in LANGUAGES:
                save_game_language(output,code)
                data=(output/'datas/Retro-Recomp.ini').read_bytes()
                # Win32 may choose UTF-16 once another entry contains Unicode.
                text=data.decode('utf-16') if data[:2] in (b'\xff\xfe',b'\xfe\xff') else data.decode('utf-8-sig')
                self.assertIn('language='+code,text.replace(' = ','='))
                self.assertTrue(language_name(code))
            with self.assertRaises(ValueError):save_game_language(output,'xx')

    def test_runtime_printf_formats_and_baked_glyph_coverage(self):
        values={c:catalog(c)['runtime'] for c in LANGUAGES[1:]}
        spec=lambda s:re.findall(r'%(?!%)[-+ #0]*\d*(?:\.\d+)?(?:ll|[hlz])?[diuoxXfFeEgGcs]',s)
        glyphs=(ASSETS/'native/runtime_glyphs.inc').read_text(encoding='ascii')
        points={int(x) for x in re.findall(r'\{(\d+),\d+,\d+\}',glyphs)}
        for code,rows in values.items():
            self.assertEqual(set(rows),set(values['fr']),code)
            for english,text in rows.items():
                self.assertEqual(spec(english),spec(text),(code,english))
                self.assertTrue({ord(c) for c in text if ord(c)>=127}<=points,(code,text))

    def test_process_font_subsets_are_small_and_valid(self):
        coverage=json.loads((ASSETS/'assets/font-coverage.json').read_text(encoding='ascii'))
        text=''.join(LANGUAGE_NAMES)+''.join(''.join(pair) for pair in STRINGS.values())
        text+=''.join(''.join(catalog(code)['ui'].values()) for code in LANGUAGES[2:])
        self.assertTrue({ord(c) for c in text if ord(c)>=32}<=set(coverage['codepoints']))
        for face in ('JP','SC'):
            data=(ASSETS/'assets'/f'RetroRecomp-UI-{face}.otf').read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),coverage['font_sha256'][face])
            self.assertEqual(data[:4],b'OTTO')
            self.assertLess(len(data),700_000)


if __name__=='__main__':unittest.main()
