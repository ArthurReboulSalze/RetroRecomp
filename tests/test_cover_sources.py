from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from PIL import Image

from smsrecomp import cover_sources as api
from smsrecomp.artwork import ArtworkError, _atomic, _catalog, _public_url, normalized, prepare_icon, resolve_cover
from smsrecomp.cover_settings import CONFIG_NAME, defaults, load_settings, save_settings


def png(transparent=False, size=(120, 180)):
    image = Image.new('RGBA', size, (20, 80, 200, 255))
    if transparent:
        image.putpixel((0, 0), (0, 0, 0, 0))
    buffer = BytesIO(); image.save(buffer, format='PNG')
    return buffer.getvalue()


class CoverSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rom = self.root / 'Game (Europe).gb'
        self.rom.write_bytes(b'authored test ROM data')
        self.game = self.root / 'build'; self.game.mkdir()
        self.art = self.root / 'BoxArt'
        self.settings = defaults()
        api._tokens.clear(); api._platforms.clear(); api._cooldown.clear()
        # Timing itself is exercised by the provider lock; don't delay fixtures.
        self.patch_clock = patch.object(api.time, 'sleep')
        self.patch_clock.start(); self.addCleanup(self.patch_clock.stop)

    def fetch(self, provider, account, responses):
        with patch.object(api, 'request', side_effect=responses) as client:
            result = api.fetch(provider, account, self.rom, 'Game', 'gb', normalize=normalized)
        return result, client

    def ss_game(self, **overrides):
        game = {'id': 1, 'systeme': {'id': '9'}, 'noms': [{'text': 'Game'}], 'medias': [
            {'type': 'ss', 'url': 'https://api.screenscraper.fr/screenshot'},
            {'type': 'box-2D', 'region': 'eu', 'url': 'https://api.screenscraper.fr/front'},
            {'type': 'box-3D', 'region': 'eu', 'url': 'https://api.screenscraper.fr/box?devpassword=secret&sspassword=private'}]}
        game.update(overrides)
        return json.dumps({'response': {'jeu': game}}).encode()

    def test_default_settings_create_no_files_and_skip_unconfigured_services(self):
        self.assertEqual(load_settings(self.root), defaults())
        self.assertFalse((self.root / CONFIG_NAME).exists())
        with patch.object(api, 'request', side_effect=AssertionError('no API credentials')):
            for provider in api.PROVIDERS:
                self.assertIsNone(api.fetch(provider, {}, self.rom, 'Game', 'gb', normalize=normalized))

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_saved_accounts_are_encrypted_and_round_trip_without_public_preferences(self):
        self.settings['accounts']['igdb'] = {'client_id': 'synthetic-id', 'client_secret': 'synthetic-secret'}
        self.settings['accounts']['screenscraper']['sspassword'] = 'synthetic-user-password'
        save_settings(self.settings, self.root)
        stored = (self.root / CONFIG_NAME).read_text()
        for text in ('synthetic-id', 'synthetic-secret', 'synthetic-user-password'):
            self.assertNotIn(text, stored)
        restored = load_settings(self.root)
        self.assertEqual(restored['accounts'], self.settings['accounts'])
        self.assertEqual(restored['box_3d'], self.settings['box_3d'])
        self.assertTrue(restored['revision'])
        self.assertFalse((self.root / 'Retro-Recomp.json').exists())

    def test_corrupt_protected_accounts_use_safe_defaults(self):
        (self.root / CONFIG_NAME).write_text(json.dumps({'box_3d': False, 'protected_accounts': '!secret!'}))
        settings = load_settings(self.root)
        self.assertFalse(settings['box_3d'])
        self.assertTrue(settings['credential_error'])
        self.assertEqual(settings['accounts'], defaults()['accounts'])

    def test_screen_scraper_prefers_real_3d_and_never_returns_authenticated_url(self):
        account = {'devid': 'id', 'devpassword': 'secret'}
        result, client = self.fetch('screenscraper', account, [self.ss_game(), png(transparent=True)])
        self.assertEqual(result.style, 'box3d')
        self.assertIsNone(result.url)
        self.assertNotIn('secret', result.source_page)
        self.assertIn('systemeid=9', client.call_args_list[0].args[0])
        self.assertIn('sha1=', client.call_args_list[0].args[0])
        self.assertNotIn('authored test ROM data', client.call_args_list[0].args[0])
        self.assertIn('/box?', client.call_args_list[1].args[0])

    def test_screen_scraper_rejects_wrong_platform_and_sequel(self):
        for game in (self.ss_game(systeme={'id': 21}), self.ss_game(noms=[{'text': 'Game II'}])):
            result, client = self.fetch('screenscraper', {'devid': 'id', 'devpassword': 'test'}, [game])
            self.assertIsNone(result)
            self.assertEqual(client.call_count, 1)

    def test_screen_scraper_accepts_documented_nested_box_groups(self):
        response = self.ss_game(medias={'media_boitiers': {'media_boitiers_3d': {
            'media_boitier_3d_eu': 'https://api.screenscraper.fr/box'}}})
        result, _ = self.fetch('screenscraper', {'devid': 'id', 'devpassword': 'test'}, [response, png()])
        self.assertEqual(result.style, 'box3d')

    def test_screenscraper_prefers_larger_real_box_and_drops_thumbnail_limits(self):
        response = self.ss_game(medias=[
            {'type': 'box-3D', 'region': 'eu', 'width': '120', 'height': '180',
             'format': 'png', 'url': 'https://api.screenscraper.fr/small'},
            {'type': 'box-3D', 'region': 'eu', 'width': '800', 'height': '1200',
             'format': 'png', 'url': 'https://api.screenscraper.fr/large?maxwidth=128&maxheight=128&devpassword=private'},
            {'type': 'box-2D', 'region': 'eu', 'width': '1600', 'height': '2400',
             'url': 'https://api.screenscraper.fr/front'}])
        result, client = self.fetch('screenscraper', {'devid': 'id', 'devpassword': 'test'},
                                    [response, png(size=(800, 1200))])
        self.assertEqual(result.style, 'box3d')
        url = client.call_args.args[0]
        self.assertIn('/large?', url)
        self.assertNotIn('maxwidth', url)
        self.assertNotIn('maxheight', url)
        self.assertIn('devpassword=private', url)

    def test_screenscraper_uses_front_when_no_real_box_exists(self):
        response = self.ss_game(medias=[{'type': 'box-2D', 'region': 'eu',
                               'url': 'https://api.screenscraper.fr/front'}])
        result, client = self.fetch('screenscraper', {'devid': 'id', 'devpassword': 'test'}, [response, png()])
        self.assertEqual(result.style, 'front')
        self.assertTrue(client.call_args.args[0].endswith('/front'))

    def tgdb(self, images=None, platform=4, title='Game'):
        return json.dumps({'data': {'games': [{'id': 7, 'platform': platform, 'game_title': title}]},
            'include': {'boxart': {'base_url': {'large': 'https://cdn.thegamesdb.net/images/large/'},
                'data': {'7': images if images is not None else [
                    {'type': 'screenshot', 'filename': 'screenshot.jpg'},
                    {'type': 'boxart', 'side': 'back', 'filename': 'back.jpg'},
                    {'type': 'boxart', 'side': 'front', 'filename': 'boxart/front/7-1.jpg'}]}}}}).encode()

    def test_thegamesdb_front_only_for_correct_console(self):
        cover, client = self.fetch('thegamesdb', {'apikey': 'test'}, [self.tgdb(), png()])
        self.assertEqual(cover.style, 'front')
        self.assertIn('front/7-1.jpg', client.call_args.args[0])
        self.assertIn('filter%5Bplatform%5D=4', client.call_args_list[0].args[0])
        for response in (self.tgdb(platform=35), self.tgdb(title='Game 2'), self.tgdb(images=[
            {'type': 'boxart', 'side': 'front', 'filename': 'a.jpg'},
            {'type': 'boxart', 'side': 'front', 'filename': 'b.jpg'}])):
            result, client = self.fetch('thegamesdb', {'apikey': 'test'}, [response])
            self.assertIsNone(result)
            self.assertEqual(client.call_count, 1)

    def test_thegamesdb_requests_original_instead_of_large_thumbnail(self):
        response = json.loads(self.tgdb())
        response['include']['boxart']['base_url']['original'] = 'https://cdn.thegamesdb.net/images/original/'
        cover, _ = self.fetch('thegamesdb', {'apikey': 'test'}, [json.dumps(response).encode(), png()])
        self.assertIn('/images/original/', cover.url)

    def test_igdb_twitch_auth_and_platform_filtered_search(self):
        replies = [json.dumps({'access_token': 'synthetic-token', 'expires_in': 3600}).encode(),
            json.dumps([{'id': 33, 'slug': 'gb'}]).encode(),
            json.dumps([{'id': 4, 'name': 'Game', 'platforms': [33], 'cover': {'image_id': 'co_test'}},
                        {'id': 5, 'name': 'Game II', 'platforms': [33], 'cover': {'image_id': 'co_wrong'}},
                        {'id': 6, 'name': 'Game', 'platforms': [64], 'cover': {'image_id': 'co_sms'}}]).encode(), png()]
        result, client = self.fetch('igdb', {'client_id': 'test', 'client_secret': 'test-secret'}, replies)
        self.assertEqual(result.style, 'front')
        self.assertIn('co_test.jpg', result.url)
        self.assertIn('/t_1080p/', result.url)
        self.assertNotIn('test-secret', client.call_args_list[0].args[0])
        self.assertIn(b'grant_type=client_credentials', client.call_args_list[0].kwargs['body'])
        self.assertIn(b'where platforms = (33)', client.call_args_list[2].kwargs['body'])

    def test_http_credentials_never_appear_in_errors_and_refusal_backs_off(self):
        url = 'https://api.thegamesdb.net/?apikey=synthetic-secret'
        error = urllib.error.HTTPError(url, 403, 'synthetic-secret', {}, None)
        with patch.object(api.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(api.CoverServiceError) as caught:
                api.request(url, 100, private=True)
        self.assertNotIn('synthetic-secret', str(caught.exception))
        self.assertTrue(caught.exception.temporary)
        with patch.object(api, 'request', side_effect=api.CoverServiceError('quota', temporary=True)) as client:
            with self.assertRaises(api.CoverServiceError):
                api.fetch('thegamesdb', {'apikey': 'test'}, self.rom, 'Game', 'gb', normalize=normalized)
            self.assertIsNone(api.fetch('thegamesdb', {'apikey': 'test'}, self.rom, 'Game', 'gb', normalize=normalized))
            self.assertEqual(client.call_count, 1)

    @unittest.skipUnless(os.name == 'nt', 'Windows HTTPS client')
    def test_frozen_https_secrets_are_on_stdin_only(self):
        with patch.object(api.sys, 'frozen', True, create=True), patch.object(api.subprocess, 'run',
            return_value=subprocess.CompletedProcess([], 0, b'{}200', b'')) as client:
            api.request('https://api.thegamesdb.net/?apikey=synthetic-secret', 100, private=True)
        self.assertNotIn('synthetic-secret', str(client.call_args.args))
        self.assertIn(b'synthetic-secret', client.call_args.kwargs['input'])
        self.assertNotIn('--location', client.call_args.args[0])

    def test_provider_failure_falls_back_and_validated_download_works_offline(self):
        self.settings['accounts']['screenscraper'] = {'devid': 'test', 'devpassword': 'test'}
        with patch('smsrecomp.artwork.fetch', side_effect=api.CoverServiceError('unavailable')), \
                patch('smsrecomp.artwork._get', return_value=png()):
            report = prepare_icon(self.game, self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(report['source'], 'libretro')
        self.assertEqual(report['box_style'], 'original')
        with patch('smsrecomp.artwork.fetch', side_effect=AssertionError('offline')), \
                patch('smsrecomp.artwork._get', side_effect=AssertionError('offline')):
            cached = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, settings=self.settings)
        self.assertEqual(report['icon_sha256'], cached['icon_sha256'])

    def test_real_3d_cache_retains_shape_and_sanitized_provenance(self):
        self.settings['accounts']['screenscraper'] = {'devid': 'test', 'devpassword': 'synthetic-secret'}
        remote = api.RemoteCover('screenscraper', png(transparent=True),
            'https://www.screenscraper.fr/gameinfos.php?gameid=1', 'box3d')
        with patch('smsrecomp.artwork.fetch', return_value=remote), \
                patch('smsrecomp.artwork._get', side_effect=AssertionError('API has a cover')):
            report = prepare_icon(self.game, self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(report['box_style'], 'source_3d')
        self.assertIsNone(report['url'])
        for file in self.art.rglob('*.json'):
            self.assertNotIn('synthetic-secret', file.read_text())
        with patch('smsrecomp.artwork.fetch', side_effect=AssertionError('cached')):
            cached = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(cached['source'], 'screenscraper_cache')

    def test_configuring_a_service_upgrades_a_flat_cache_without_redownloading_public_art(self):
        with patch('smsrecomp.artwork._get', return_value=png()):
            initial = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(initial['source'], 'libretro')
        self.settings['accounts']['screenscraper'] = {'devid': 'test', 'devpassword': 'test'}
        remote = api.RemoteCover('screenscraper', png(transparent=True),
            'https://www.screenscraper.fr/gameinfos.php?gameid=1', 'box3d')
        with patch('smsrecomp.artwork.fetch', return_value=remote) as fetch, \
                patch('smsrecomp.artwork._get', side_effect=AssertionError('public cache already exists')):
            upgraded = resolve_cover(self.rom, 'Game', self.root / 'empty', cache_directory=self.art,
                                     settings=self.settings)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(upgraded['source'], 'screenscraper')

    def test_api_upgrade_failure_keeps_the_valid_existing_cover(self):
        with patch('smsrecomp.artwork._get', return_value=png()):
            initial = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.settings['accounts']['thegamesdb']['apikey'] = 'test'
        with patch('smsrecomp.artwork.fetch', side_effect=api.CoverServiceError('offline')), \
                patch('smsrecomp.artwork._get', side_effect=AssertionError('keep valid cover')):
            cached = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(initial['data'], cached['data'])
        with patch('smsrecomp.artwork.fetch', side_effect=AssertionError('configuration already checked')):
            resolve_cover(self.rom, 'Game', self.art, settings=self.settings)

    def test_previous_thumbnail_cache_is_checked_once_for_an_hd_source(self):
        self.settings['accounts']['screenscraper'] = {'devid': 'test', 'devpassword': 'test'}
        small = api.RemoteCover('screenscraper', png(transparent=True),
                    'https://www.screenscraper.fr/gameinfos.php?gameid=1', 'box3d')
        with patch('smsrecomp.artwork.fetch', return_value=small):
            initial = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        metadata = initial['path'].with_suffix('.png.json')
        record = json.loads(metadata.read_text())
        record.pop('checked_image_policy')
        metadata.write_text(json.dumps(record))
        large = api.RemoteCover('screenscraper', png(transparent=True, size=(800, 1200)),
                    small.source_page, 'box3d')
        with patch('smsrecomp.artwork.fetch', return_value=large) as client:
            upgraded = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(client.call_count, 1)
        with Image.open(BytesIO(upgraded['data'])) as image:
            self.assertEqual(image.size, (800, 1200))
        with patch('smsrecomp.artwork.fetch', side_effect=AssertionError('HD source already checked')):
            cached = resolve_cover(self.rom, 'Game', self.art, settings=self.settings)
        self.assertEqual(upgraded['data'], cached['data'])

    def test_front_fallback_keeps_shape_and_pixels_without_a_fabricated_spine(self):
        self.art.mkdir(); (self.art / 'Game (Europe).png').write_bytes(png())
        first = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, settings=self.settings)
        self.assertEqual(first['box_style'], 'original')
        with Image.open(self.game / 'game-icon.png') as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.size, (256, 256))
            visible = image.crop(image.getchannel('A').getbbox())
            self.assertEqual(visible.height, 256)
            self.assertAlmostEqual(visible.width / visible.height, 2/3, places=2)
            self.assertEqual(visible.getextrema(), ((20, 20), (80, 80), (200, 200), (255, 255)))
        self.settings['box_3d'] = False
        flat = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, settings=self.settings)
        self.assertEqual(flat['box_style'], 'original')
        self.assertEqual(first['icon_sha256'], flat['icon_sha256'])

    def test_high_resolution_source_is_preserved_and_largest_icon_fills_256_pixels(self):
        self.art.mkdir()
        source = png(size=(1200, 1800))
        path = self.art / 'Game (Europe).png'
        path.write_bytes(source)
        report = prepare_icon(self.game, self.rom, 'Game', self.art, online=False, settings=self.settings)
        self.assertEqual(path.read_bytes(), source)
        self.assertEqual(report['image_size'], [1200, 1800])
        self.assertTrue(report['source_resolution_sufficient'])
        self.assertEqual(report['largest_icon_size'], 256)
        with Image.open(self.game / 'game.ico') as icon:
            image = icon.ico.getimage((256, 256))
            bounds = image.getchannel('A').getbbox()
            self.assertEqual(bounds[3] - bounds[1], 256)

    def test_complete_libretro_catalog_keeps_entries_after_1000_and_rejects_truncated_tree(self):
        rows = [{'type': 'blob', 'path': f'Named_Boxarts/Game {n}.png'} for n in range(1100)]
        rows += [{'type': 'blob', 'path': 'Named_Snaps/Game.png'}]
        with patch('smsrecomp.artwork._get', return_value=json.dumps({'truncated': False, 'tree': rows}).encode()):
            catalog = _catalog(self.art, 'gb')
        self.assertEqual(len(catalog), 1100)
        self.assertIn('Game 1099.png', catalog)

    def test_public_metadata_drops_authenticated_links(self):
        for query in ('apikey=test', 'devpassword=test', 'sspassword=test', 'access_token=test'):
            self.assertIsNone(_public_url('https://api.example.test/?' + query))
        self.assertEqual(_public_url('https://thegamesdb.net/game.php?id=1'), 'https://thegamesdb.net/game.php?id=1')

    @unittest.skipUnless(os.name == 'nt', 'Windows UNC sources')
    def test_network_artwork_sources_cannot_receive_cache_writes(self):
        network = Path('\\\\example.test\\artwork\\cover.png')
        with patch.object(Path, 'mkdir', side_effect=AssertionError('source collection is read-only')):
            with self.assertRaises(ArtworkError):
                _atomic(network, png())


if __name__ == '__main__':
    unittest.main()
