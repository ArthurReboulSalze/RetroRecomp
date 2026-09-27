"""Exercise default portable paths with real fallback, migration and reconversion."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, convert, read_rom
from smsrecomp.library import GameMemory


def main():
    base = ROOT / '.build/data-selftest'
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=base))
    shared = work / 'jeux partagés'; shared.mkdir()
    elsewhere = work / 'ailleurs'; elsewhere.mkdir()
    sentinel = elsewhere / 'dispatch_misses.log'
    sentinel.write_bytes(b'Legacy file must remain untouched.')
    legacy = shared / 'SMSRecomp.ini'
    legacy.write_text('[Clavier]\nbouton1=C\n[Video]\nfiltre=3\n', encoding='ascii')
    old = legacy.read_bytes()
    os.environ.pop('RETRO_RECOMP_LIBRARY_DIR', None)
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(work / 'converter-library-first')
    env = os.environ.copy()
    env.pop('SMSRECOMP_LIBRARY_DIR', None)
    env.pop('RETRO_RECOMP_LIBRARY_DIR', None)
    env.pop('SMSRECOMP_STRICT', None)
    env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    roms = []
    for index, value in enumerate((0xA5, 0x5A)):
        data = bytearray([0xC9] * 8192)
        data[:3] = bytes.fromhex('C3 00 01')
        program = bytes.fromhex('F3 31 F0 DF 3E 00 32 00 C0 3E 02 32 01 C0 2A 00 C0 E9')
        data[0x100:0x100+len(program)] = program
        data[0x200:0x209] = bytes([0x3E,value,0x32,0x10,0xC0,0x76,0xC3,0x05,0x02])
        rom = work / f'Authored_{index}.sms'; rom.write_bytes(data); roms.append(rom)
        generated = convert(rom, title=f'DataGame{index}', output=work/f'conversion{index}',
            backend="functions", passes=1, frames=3, online_cover=False, use_cover=False, emit=lambda text: None)
        copied = shared / f'Renamed_{index}.exe'; shutil.copy2(generated, copied)
        result = subprocess.run([str(copied), '--headless', '--window', '3', '--frames', '3', '--mute'],
            cwd=elsewhere, env=env, timeout=15)
        assert result.returncode == 0
        memory = GameMemory(read_rom(rom), shared/'datas/library')
        assert memory.summary()['rom_entries'] >= 1
        key = f'DataGame{index}-{read_rom(rom).sha256[:12]}'
        game = shared/'datas/games'/key
        assert (game/f'DataGame{index}-last-run.log').exists()
        assert (game/f'DataGame{index}-dispatch-misses.log').exists()
        assert '-> hybrid' in (game/f'DataGame{index}-last-run.log').read_text()
    ini = shared / 'datas/Retro-Recomp.ini'
    assert legacy.read_bytes() == old
    import configparser
    original_config = configparser.ConfigParser(); original_config.read_string(old.decode('ascii'))
    migrated_config = configparser.ConfigParser(); migrated_config.read(ini, encoding='ascii')
    for section in original_config:
        for key, value in original_config[section].items():
            assert migrated_config[section][key] == value
    assert migrated_config['ClavierJ2']['bouton1'] == 'Keypad 8'
    migrated_bytes = ini.read_bytes()
    assert sentinel.read_bytes() == b'Legacy file must remain untouched.'
    assert {p.name for p in shared.iterdir()} == {'Renamed_0.exe','Renamed_1.exe','SMSRecomp.ini','datas'}
    assert list(elsewhere.iterdir()) == [sentinel]
    # Start a fresh converter library. Only the standalone game's portable
    # observations may seed this generation (not the initial conversion).
    os.environ['SMSRECOMP_LIBRARY_DIR'] = str(work / 'converter-library-second')
    second = convert(roms[0], title='DataGame0_Rebuilt', output=shared/'datas/reports/rebuilt',
        backend="functions", passes=1, frames=3, online_cover=False, use_cover=False, emit=lambda text: None)
    report = json.loads((second.parent/'conversion-report.json').read_text(encoding='utf-8'))
    assert report['learning']['imported_legacy_observations'] >= 1
    assert all(c['passed'] and c['interpreter_cycles'] == 0 for c in report['strict_checks'])
    assert ini.read_bytes() == migrated_bytes
    (base/'verification.json').write_text(json.dumps({'work':str(work), 'named_fallback_logs':True,
        'two_games_isolated':True, 'shared_ini_migrated_and_preserved':True,
        'legacy_cwd_file_preserved':True, 'portable_learning_reimported':True}, indent=2), encoding='utf-8')
    print('PASS: real fallback writes named files only in datas; two games stay isolated, legacy INI/file preserved, portable discoveries seed a fresh converter with zero fallback.')

if __name__ == '__main__':
    main()
