"""Real title variations plus adversarial sequel and ambiguity cases."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

from PIL import Image

from smsrecomp.artwork import choose_cover, normalized, resolve_cover
from smsrecomp import cover_sources as api
from smsrecomp.cover_titles import matching_indices, search_queries


def png():
    stream = BytesIO()
    Image.new('RGB', (300, 420), 'white').save(stream, format='PNG')
    return stream.getvalue()


class CoverTitleTests(unittest.TestCase):
    def test_spelling_articles_abbreviations_and_numerals(self):
        cases = (
            ('Super Metriod', 'Super Metroid'),
            ('Super Mario Brothers III', 'Super Mario Bros. 3'),
            ("Bill & Ted's Excellent Adventure", "Bill and Ted's Excellent Adventure"),
            ('The Legend of Zelda', 'Legend of Zelda, The'),
            ('Pokemon', 'Pok\u00e9mon'),
            ('Disney\u2019s Aladdin', 'Aladdin'),
            ('Mortal Kombat II', 'Mortal Kombat 2'),
        )
        for query, candidate in cases:
            with self.subTest(query=query):
                self.assertEqual(choose_cover([candidate + ' (USA).png'], query, query),
                                 candidate + ' (USA).png')

    def test_short_titles_and_verified_alias_work_in_complete_catalogue(self):
        names = ['Advanced Daisenryaku - Deutsch Dengeki Sakusen (Japan).png',
                 'A Ressha de Ikou MD (Japan).png', 'Air Diver (USA).png']
        self.assertEqual(choose_cover(names, 'Advanced Daisenryaku (Japan)',
                                     'Advanced Daisenryaku'), names[0])
        self.assertEqual(choose_cover(names, 'A Ressha de Gyoukou MD (Japan)',
                                     'A Ressha de Gyoukou MD'), names[1])

    def test_edition_preference_after_tolerant_title_match(self):
        names = ['Double Dragon III - The Arcade Game (Japan).png',
                 'Double Dragon III - The Arcade Game (USA).png']
        self.assertEqual(choose_cover(names, 'Double Dragon 3 (USA)', 'Double Dragon 3'), names[1])
        with self.assertRaises(ValueError):
            choose_cover(names, 'Double Dragon 3', 'Double Dragon 3')

    def test_sequels_years_and_x_series_are_never_substituted(self):
        cases = (('Strider II', 'Strider'), ('Strider II', 'Strider III'),
                 ('Sonic 3', 'Sonic 2'), ('Mega Man X', 'Mega Man 10'),
                 ('Mega Man X2', 'Mega Man X'),
                 ("World Cup Italia '90", "World Cup Italia '94"),
                 ('Fighting Simulator 2 in 1', 'Fighting Simulator'))
        for query, candidate in cases:
            with self.subTest(query=query, candidate=candidate):
                for regional in (False, True):
                    self.assertIsNone(choose_cover([candidate + ' (USA).png'], query, query,
                                                  regional_fallback=regional))
        # Even an erroneous truncated display title cannot choose the first game.
        self.assertIsNone(choose_cover(['Strider (USA).png'], 'Strider II (USA)', 'Strider'))

    def test_ambiguous_subtitles_typos_and_short_titles_do_not_guess(self):
        self.assertEqual(matching_indices(['Super Mario - Land', 'Super Mario - World'],
                                          'Super Mario', 'Super Mario'), [])
        self.assertEqual(matching_indices(['Brain Lord', 'Brain Land'], 'Brain Lard', 'Brain Lard'), [])
        self.assertEqual(matching_indices(['Sonic'], 'Soniq', 'Soniq'), [])
        self.assertEqual(matching_indices(['Super Mario World'], 'Super Mario Land', 'Super Mario Land'), [])

    def test_exact_cover_keeps_priority_over_spelling_tolerance(self):
        names = ['Super Metriod (USA).png', 'Super Metroid (USA).png']
        self.assertEqual(choose_cover(names, 'Super Metriod (USA)', 'Super Metriod'), names[0])

    def test_original_title_beats_modified_subtitle_when_spelling_is_wrong(self):
        names = ['Super Metroid - Redux (USA).png', 'Super Metroid (World).png',
                 'Super Metroid - Redesign (USA).png']
        self.assertEqual(choose_cover(names, 'Super Metriod', 'Super Metriod',
                                     regional_fallback=True), names[1])
        self.assertIsNone(choose_cover([names[0]], 'Super Metroid', 'Super Metroid',
                                       regional_fallback=True))
        self.assertEqual(choose_cover([names[0]], 'Super Metroid - Redux (USA)',
                                     'Super Metroid - Redux'), names[0])

    def test_full_title_spelling_match_beats_near_shortened_title(self):
        names = ['Super Metroid - Other Adventure (USA).png', 'Super Metroid (USA).png']
        self.assertEqual(choose_cover(names, 'Super Metriod', 'Super Metriod'), names[1])
        self.assertIsNone(choose_cover(['Game (USA) (Hack).png'], 'Game (USA)', 'Game'))

    def test_local_matching_shared_by_every_supported_console_preserves_sources(self):
        cases = {'sms': ('Mortal Kombat 2', 'Mortal Kombat II'),
                 'gg': ('Disney\u2019s Aladdin', 'Aladdin'),
                 'gb': ('Double Dragon 3', 'Double Dragon III - The Arcade Game'),
                 'nes': ('Super Mario Brothers 3', 'Super Mario Bros. 3'),
                 'md': ('Advanced Daisenryaku', 'Advanced Daisenryaku - Deutsch Dengeki Sakusen'),
                 'snes': ('Super Metriod', 'Super Metroid')}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for system, (query, candidate) in cases.items():
                with self.subTest(system=system):
                    directory = root / system
                    directory.mkdir()
                    source = directory / (candidate + ' (USA).png')
                    data = png()
                    source.write_bytes(data)
                    with patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
                        cover = resolve_cover(root / (query + ' (USA).rom'), query, directory,
                                              online=False, system_id=system, emit=lambda _: None)
                    self.assertEqual(cover['path'], source)
                    self.assertEqual(source.read_bytes(), data)
                    self.assertEqual(list(directory.iterdir()), [source])

    def test_api_query_variants_are_bounded_and_keep_sequel_numbers(self):
        self.assertEqual(search_queries('Game (USA)', 'Game'), ['Game'])
        self.assertEqual(search_queries('A Ressha de Gyoukou MD (Japan)', 'A Ressha de Gyoukou MD'),
                         ['A Ressha de Gyoukou MD', 'A Ressha de Ikou MD'])
        queries = search_queries('Mortal Kombat II (USA)', 'Mortal Kombat II')
        self.assertIn('Mortal Kombat 2', queries)
        self.assertNotIn('Mortal Kombat', queries)
        self.assertLessEqual(len(queries), 3)


class CoverTitleProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rom = self.root / 'A Ressha de Gyoukou MD (Japan).md'
        self.rom.write_bytes(b'authored provider fixture')
        api._tokens.clear(); api._platforms.clear(); api._cooldown.clear()
        timer = patch.object(api.time, 'sleep')
        timer.start(); self.addCleanup(timer.stop)

    def test_thegamesdb_retries_verified_alias_without_losing_console_filter(self):
        replies = [json.dumps({'data': {'games': []}}).encode(),
                   json.dumps({'data': {'games': [
                       {'id': 7, 'platform': 18, 'game_title': 'A Ressha de Ikou MD'},
                       {'id': 8, 'platform': 7, 'game_title': 'A Ressha de Gyoukou MD'}]},
                       'include': {'boxart': {'base_url': {'original': 'https://cdn.thegamesdb.net/original/'},
                           'data': {'7': [{'type': 'boxart', 'side': 'front', 'filename': '7.png'}]}}}}).encode(), png()]
        with patch.object(api, 'request', side_effect=replies) as request:
            cover = api.fetch('thegamesdb', {'apikey': 'test'}, self.rom,
                              'A Ressha de Gyoukou MD', 'md', normalize=normalized)
        self.assertEqual(cover.url, 'https://cdn.thegamesdb.net/original/7.png')
        for call in request.call_args_list[:2]:
            self.assertIn('filter%5Bplatform%5D=18', call.args[0])
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args_list[1].args[0]).query)
        self.assertEqual(params['name'], ['A Ressha de Ikou MD'])

    def test_igdb_retries_alias_and_filters_another_console(self):
        replies = [json.dumps({'access_token': 'synthetic', 'expires_in': 3600}).encode(),
                   json.dumps([{'id': 29, 'slug': 'genesis-slash-megadrive'}]).encode(), b'[]',
                   json.dumps([{'id': 7, 'name': 'A Ressha de Ikou MD', 'platforms': [29],
                                'cover': {'image_id': 'co_good'}},
                               {'id': 8, 'name': 'A Ressha de Gyoukou MD', 'platforms': [99],
                                'cover': {'image_id': 'co_wrong'}}]).encode(), png()]
        with patch.object(api, 'request', side_effect=replies) as request:
            cover = api.fetch('igdb', {'client_id': 'test', 'client_secret': 'test'}, self.rom,
                              'A Ressha de Gyoukou MD', 'md', normalize=normalized)
        self.assertIn('co_good', cover.url)
        self.assertIn(b'A Ressha de Ikou MD', request.call_args_list[3].kwargs['body'])
        self.assertIn(b'platforms = (29)', request.call_args_list[3].kwargs['body'])

    def test_screenscraper_uses_tolerant_names_without_relaxing_system(self):
        rom = self.root / 'Super Metriod (USA).sfc'
        rom.write_bytes(b'authored SNES provider fixture')
        game = {'id': 7, 'systeme': {'id': 4}, 'noms': [{'text': 'Super Metroid'}],
                'medias': [{'type': 'box-2D', 'region': 'us',
                            'url': 'https://api.screenscraper.fr/front'}]}
        response = json.dumps({'response': {'jeu': game}}).encode()
        with patch.object(api, 'request', side_effect=[response, png()]):
            cover = api.fetch('screenscraper', {'devid': 'test', 'devpassword': 'test'},
                              rom, 'Super Metriod', 'snes', normalize=normalized)
        self.assertEqual(cover.style, 'front')
        game['systeme']['id'] = 1
        with patch.object(api, 'request', return_value=json.dumps({'response': {'jeu': game}}).encode()) as request:
            self.assertIsNone(api.fetch('screenscraper', {'devid': 'test', 'devpassword': 'test'},
                                      rom, 'Super Metriod', 'snes', normalize=normalized))
        self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
