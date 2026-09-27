"""Regenerate with the packaged app while an isolated generated game runs.

Uses only an authored ROM and SDL dummy drivers. Never stops a user's game.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT
from smsrecomp import __version__
from smsrecomp.paths import export_directory
from smsrecomp.publishing import is_pending, _running


def main():
    directory = ROOT / '.build/packaged091-check'
    directory.mkdir(parents=True, exist_ok=True)
    shared = directory / 'jeux partagés'
    rom = directory / 'Regeneration Test.sms'
    data = bytearray([0xC9] * 8192)
    data[:8] = bytes.fromhex('F3 31 F0 DF 00 C3 04 00')
    rom.write_bytes(data)
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
               RETRO_RECOMP_LIBRARY_DIR=str(directory / 'library'))
    app = export_directory() / 'Retro-Recomp.exe'
    command = [str(app), 'batch', str(rom), '--output', str(shared), '--frames', '10',
               '--passes', '1', '--no-cover', '--no-online-cover']
    def convert(name):
        with (directory / name).open('wb') as log:
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=log, timeout=180)
        assert completed.returncode == 0, name
        record = json.loads((shared / 'datas/Retro-Recomp-batch.json').read_text())
        assert record['failed'] == 0 and record['succeeded'] == 1, record
        return record
    first = convert('first-conversion.log')
    target = Path(first['games'][0]['executable'])
    assert target.name == 'Regeneration Test.exe'
    ini = shared / 'datas/Retro-Recomp.ini'
    custom = configparser.ConfigParser(); custom.read(ini, encoding='ascii')
    for section, key, value in (('Clavier', 'bouton1', 'C'), ('ClavierJ2', 'bouton1', 'V'),
                                ('Video', 'filtre', '3')):
        if not custom.has_section(section):
            custom.add_section(section)
        custom.set(section, key, value)
    with ini.open('w', encoding='ascii') as file:
        custom.write(file)
    # This is our own authored game under .build, never a commercial game.
    with (directory / 'isolated-game.log').open('wb') as log:
        game = subprocess.Popen([str(target), '--headless', '--window', '1', '--frames', '100000',
            '--mute', '--strict'], cwd=directory, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 15
        while not ini.exists() and time.monotonic() < deadline:
            assert game.poll() is None, 'Isolated game exited before creating its config'
            time.sleep(.1)
        assert ini.exists() and _running(target)
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        second = convert('regeneration-while-running.log')
        result = second['games'][0]
        assert result['pending_install'] and is_pending(target), result
        assert Path(result['executable']) == target and game.poll() is None
        assert hashlib.sha256(target.read_bytes()).hexdigest() == before
        report = json.loads(Path(result['report']).read_text())
        assert report['version'] == __version__ and report['backend'] == 'banked'
        expected = hashlib.sha256(Path(report['build_executable']).read_bytes()).hexdigest()
    finally:
        game.terminate()  # Only the test process created immediately above.
        game.wait(timeout=10)
    # The converter has already exited; its detached packaged installer works.
    deadline = time.monotonic() + 20
    while is_pending(target) and time.monotonic() < deadline:
        time.sleep(.1)
    assert not is_pending(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    config = configparser.ConfigParser(); config.read(ini, encoding='ascii')
    assert config['Clavier']['bouton1'] == 'C' and config['ClavierJ2']['bouton1'] == 'V'
    assert config['Video']['filtre'] == '3'
    assert all(check['interpreter_cycles'] == 0 for check in report['final_checks'])
    # One more reconversion, with the game closed: no pending state or collision.
    third = convert('regeneration-closed.log')
    assert not third['games'][0]['pending_install']
    assert Path(third['games'][0]['executable']) == target
    proof = {'version': report['version'], 'converter_sha256': hashlib.sha256(app.read_bytes()).hexdigest(),
             'title_filename': target.name, 'running_game_preserved': True,
             'packaged_installer_after_converter_exit': True, 'closed_regeneration_reuses_name': True,
             'custom_controls_and_filter_preserved': True, 'fallback_cycles': 0}
    (directory / 'verification.json').write_text(json.dumps(proof, indent=2))
    print('PASS: packaged conversion/regeneration, running game preserved, deferred install after app exit, '
          'same readable filename and custom controls/filter preserved.')


if __name__ == '__main__':
    main()
