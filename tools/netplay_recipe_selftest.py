"""The multiplayer recipe on real conversions, with an authored Master System program; no commercial game.

Two players are played here by two libraries under .build/netplay-recipe-selftest, each conversion through the
ordinary command line (`RetroRecomp.py convert`, `recipe make`, `recipe apply`), headless:

  host    converts the program from a file named "... (Europe)" (so PAL by its name), with a library L1 that holds
          a ROM entry and a RAM window found in the ROM: its record is not empty; then makes the recipe;
  empty   the same file with an empty library: the same identity as the host's (on the banked engine a path that
          has a position in the ROM does not change the generated sources; said, not hidden);
  named   the same bytes from a file with another name (NTSC by its name), empty library: another identity, by
          the name alone;
  guest   that other name again, with a library L2 that holds a RAM window that is nowhere in the ROM (private,
          compiled natively): another identity again, by the window alone;
  recipe  the guest applies the host's recipe, with L2 as its library: the host's identity, PAL, the host's one
          window and not L2's; L2 and the guest's banks are byte-identical before and after;
  refusals: the guest's own conversion has no recipe (its private window cannot travel as numbers); another dump;
          another converter version; a record with a non-numeric row, with too many rows, naming another game; an
          output folder inside the games folder.

The result is printed as JSON and written to .build/netplay-recipe-selftest/result.json.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(Path(__file__).resolve().parent))

HOST_NAME = 'Authored Recipe (Europe)'
GUEST_NAME = 'my own dump'
ROUTINE = 0x200
ROM_WINDOW = '3E00D3BF'       # four bytes of the program's main loop: they have a position in the ROM
PRIVATE_WINDOW = 'DD360512'   # LD (IX+5),12h: nowhere in the program, as code a game would build in RAM


def authored_program() -> bytes:
    """The program of tools/simulation_identity_selftest.py with one more routine nothing calls (XOR A; RET at
    0200h), so that a library can hold a ROM entry for it."""
    from simulation_identity_selftest import authored_program as base
    data = bytearray(base())
    data[ROUTINE:ROUTINE + 2] = bytes.fromhex('AF C9')
    return bytes(data)


def entry_line(data: bytes, address: int) -> str:
    """A ROM entry as the library's journal holds it: address, the three mapper slots, the FNV of its 256 bytes."""
    value = 2166136261
    for byte in data[address:address + 256]:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return f'{address:04X} 00 01 02 {value:08X}\n'


def tree_digest(folder: Path) -> str:
    """Every file below a folder, by relative name and content ('absent' when there is no folder)."""
    if not folder.is_dir():
        return 'absent'
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob('*') if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def environment(library: Path) -> dict:
    values = dict(os.environ)
    for name in ('RETRO_RECOMP_KEEP_BUILD', 'RETRO_RECOMP_RECIPE_DIR', 'SMSRECOMP_LIBRARY_DIR'):
        values.pop(name, None)
    values.update(RETRO_RECOMP_LIBRARY_DIR=str(library), SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    if os.name == 'nt':
        values.setdefault('RETRO_RECOMP_TOOLCHAIN', 'llvm')
    return values


def command(*arguments, library: Path, log: Path):
    done = subprocess.run([sys.executable, '-B', str(REPOSITORY / 'RetroRecomp.py'), *map(str, arguments)],
                          cwd=REPOSITORY, env=environment(library), capture_output=True, text=True, encoding='utf-8',
                          errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(done.stdout + done.stderr, encoding='utf-8')
    return done


def described(report_path: Path) -> dict:
    from retrorecomp.report_schema import read_report
    document = json.loads(report_path.read_text(encoding='utf-8'))
    before = document['learning']['before']
    return {'report': str(report_path), 'record': read_report(document)['simulation_identity'],
            'standard': document['video_model']['standard'],
            'windows_before': before['native_pattern_windows'], 'rom_entries_before': before['rom_entries'],
            'windows_compiled': document['learning']['native_profiles']['compiled_windows']}


def convert(work: Path, name: str, rom: Path, library: Path) -> dict:
    """One ordinary conversion into a folder of its own; what the comparison needs of its report."""
    folder = work / name
    shutil.rmtree(folder, ignore_errors=True)
    done = command('convert', rom, '--title', 'Authored Recipe', '--output', folder / 'games', '--no-online-cover',
                   '--no-compress', '--no-cover', '--frames', '600', '--passes', '2',
                   library=library, log=folder / 'conversion.log')
    if done.returncode:
        raise SystemExit(f'{name}: the conversion failed; see {folder / "conversion.log"}\n' + done.stderr[-2000:])
    reports = sorted((folder / 'games').rglob('conversion-report.json'))
    if len(reports) != 1:
        raise SystemExit(f'{name}: expected one conversion report, found {len(reports)}')
    return {'name': name, **described(reports[0])}


def refusal(action) -> dict:
    from retrorecomp.netplay_recipe import RecipeError
    try:
        action()
    except RecipeError as error:
        return {'refused': True, 'kind': error.kind, 'reason': error.reason}
    return {'refused': False}


def run() -> dict:
    from retrorecomp import netplay_recipe
    from retrorecomp.knowledge import FIELDS
    from retrorecomp.paths import ROOT, data_directory, games_root
    from retrorecomp.simulation_identity import same_simulation
    work = ROOT / '.build' / 'netplay-recipe-selftest'
    shutil.rmtree(work, ignore_errors=True)
    data = authored_program()
    identity = hashlib.sha256(data).hexdigest()
    roms = {}
    for who, name in (('host', HOST_NAME), ('guest', GUEST_NAME)):
        roms[who] = work / 'roms' / who / (name + '.sms')
        roms[who].parent.mkdir(parents=True)
        roms[who].write_bytes(data)
    other = work / 'roms' / 'other' / 'another program.sms'
    other.parent.mkdir(parents=True)
    from simulation_identity_selftest import authored_program as other_program
    other.write_bytes(other_program())
    libraries = {name: work / 'libraries' / name for name in ('host', 'empty', 'named', 'guest')}
    for folder in libraries.values():
        folder.mkdir(parents=True)
    (libraries['host'] / identity).mkdir()
    (libraries['host'] / identity / 'observations.log').write_text(entry_line(data, ROUTINE), encoding='ascii')
    (libraries['host'] / identity / 'native.patterns').write_text(ROM_WINDOW + '\n', encoding='ascii')
    (libraries['guest'] / identity).mkdir()
    (libraries['guest'] / identity / 'native.patterns').write_text(PRIVATE_WINDOW + '\n', encoding='ascii')

    host = convert(work, 'host', roms['host'], libraries['host'])
    empty = convert(work, 'empty', roms['host'], libraries['empty'])
    named = convert(work, 'named', roms['guest'], libraries['named'])
    guest = convert(work, 'guest', roms['guest'], libraries['guest'])
    runs, checks = [host, empty, named, guest], {}

    recipe_file = work / 'host.rrrecipe'
    made = command('recipe', 'make', host['report'], '--output', recipe_file, library=libraries['host'],
                   log=work / 'recipe-make.log')
    if made.returncode:
        raise SystemExit('recipe make failed:\n' + made.stderr[-2000:])
    recipe = netplay_recipe.read_recipe(recipe_file)
    record = recipe['paths']['knowledge']
    checks['recipe_names_the_dump_not_its_bytes'] = (recipe['rom_sha256'] == identity and recipe['name'] == HOST_NAME
                                                    and same_simulation(recipe['identity'], host['record']))
    checks['recipe_record_not_empty'] = bool(record.get('games')) and f'[{ROUTINE}]' in json.dumps(record)
    checks['recipe_is_small'] = recipe_file.stat().st_size < 4096
    checks['host_is_pal_by_its_name_guest_ntsc'] = host['standard'] == 'pal' and guest['standard'] == 'ntsc'
    checks['guest_plain_other_identity'] = (isinstance((guest['record'] or {}).get('identity'), str)
                                            and not same_simulation(guest['record'], host['record']))
    checks['guest_private_window_compiled'] = guest['windows_compiled'] == 1
    different = lambda first, second: (isinstance((first['record'] or {}).get('identity'), str)
                                       and isinstance((second['record'] or {}).get('identity'), str)
                                       and not same_simulation(first['record'], second['record']))
    checks['the_name_alone_changes_the_identity'] = different(named, empty)
    checks['the_private_window_alone_changes_the_identity'] = different(guest, named)
    # Said, not hidden: on the banked engine the host's carriable record does not change the generated sources.
    carriable_changes_sources = not same_simulation(empty['record'], host['record'])

    # The guest applies the recipe with L2 as its library; nothing of the guest's may change.
    guarded = {'guest_library': libraries['guest'], 'guest_banks': data_directory() / 'knowledge',
               'guest_default_library': data_directory() / 'library', 'guest_usual_export': work / 'guest' / 'games'}
    before = {name: tree_digest(folder) for name, folder in guarded.items()}
    output = work / 'recipe' / 'games'
    applied = command('recipe', 'apply', recipe_file, roms['guest'], '--output', output, '--no-compress',
                      library=libraries['guest'], log=work / 'recipe-apply.log')
    after = {name: tree_digest(folder) for name, folder in guarded.items()}
    try:
        answer = json.loads(applied.stdout)
    except ValueError:
        raise SystemExit('recipe apply failed:\n' + (applied.stdout + applied.stderr)[-3000:])
    recipe_run = {'name': 'recipe', **described(Path(answer['report']))}
    runs.append(recipe_run)
    checks['recipe_same_identity_as_host'] = (answer['same'] is True and applied.returncode == 0
                                              and same_simulation(recipe_run['record'], host['record']))
    checks['recipe_conversion_read_the_hosts_record'] = (recipe_run['standard'] == 'pal'
                                                         and recipe_run['rom_entries_before'] == 1
                                                         and recipe_run['windows_before'] == 1
                                                         and (answer['imported'] or {}).get('new') == 1)
    checks['guest_library_and_banks_unchanged'] = before == after and before['guest_library'] != 'absent'
    checks['work_folder_removed'] = not (output / netplay_recipe.WORK_FOLDER).exists()

    # Refusals. The guest's own export runs a private window: it has no recipe.
    private = command('recipe', 'make', guest['report'], '--output', work / 'guest.rrrecipe', library=libraries['guest'],
                      log=work / 'recipe-make-guest.log')
    refusals = {'host_private_window': {'refused': private.returncode != 0 and not (work / 'guest.rrrecipe').exists(),
                                       'reason': private.stderr.strip().splitlines()[-1] if private.stderr.strip() else ''}}
    refusals['other_dump'] = refusal(lambda: netplay_recipe.check_recipe(recipe, other))
    refusals['other_converter_version'] = refusal(lambda: netplay_recipe.validate_recipe({**recipe, 'converter': '0.0.1'}))

    def tampered(change):
        document = copy.deepcopy(recipe)
        change(document, next(iter(document['paths']['knowledge']['games'].values())))
        return refusal(lambda: netplay_recipe.validate_recipe(document))

    def table(game):
        """The record's ROM entries as schema 3 keeps them: one column of numbers per field."""
        return game['cpus']['z80']['paths']['entries'][0]['table']

    def overfill(document, game):
        rows = FIELDS['sms']['rom_entries'][1] + 1
        for column in table(game)['cols']:
            column['v'] = [column['v'][0]] * rows
        table(game)['cols'][0]['v'] = list(range(rows))
        table(game)['n'] = rows

    refusals['non_numeric_row'] = tampered(lambda document, game: table(game)['cols'][0]['v'].__setitem__(0, 'C3 00 02'))
    refusals['too_many_rows'] = tampered(overfill)
    refusals['another_game'] = tampered(lambda document, game: document['paths']['knowledge']['games'].__setitem__(
        'sms:' + 'b' * 64, {**copy.deepcopy(game), 'game': 'sms:' + 'b' * 64}))
    refusals['games_folder_as_output'] = refusal(
        lambda: netplay_recipe.apply_recipe(recipe, roms['guest'], games_root() / 'Master System'))
    expected = {'host_private_window': None, 'other_dump': 'rom', 'other_converter_version': 'converter',
                'non_numeric_row': 'invalid', 'too_many_rows': 'invalid', 'another_game': 'invalid',
                'games_folder_as_output': 'output'}
    for name, kind in expected.items():
        checks['refused_' + name] = refusals[name]['refused'] and (kind is None or refusals[name]['kind'] == kind)
    checks['refused_host_private_window'] &= 'RAM' in refusals['host_private_window']['reason']
    result = {'commercial_rom_used': False, 'identity_host': (host['record'] or {}).get('identity'),
              'identity_other_name': (named['record'] or {}).get('identity'),
              'identity_guest_plain': (guest['record'] or {}).get('identity'),
              'identity_guest_recipe': answer['identity'],
              'carriable_record_changes_the_sources': carriable_changes_sources,
              'recipe_bytes': recipe_file.stat().st_size, 'recipe_paths': record, 'imported': answer['imported'],
              'guarded_before': before, 'guarded_after': after, 'refusals': refusals,
              'checks': checks, 'passed': all(checks.values()), 'runs': runs}
    (work / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
