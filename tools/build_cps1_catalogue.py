"""Build the ROM-free CPS-1 catalogue from pinned MAME driver sources.

Development tool only: the converter reads the generated JSON, never MAME.
The two driver files are BSD-3-Clause (copyright-holders: Paul Leaman); the
catalogue keeps their revision, hashes and notice. Unknown ROM macros, hash
flags or board fields stop the build instead of being guessed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mame_driver_parse import (MAME_REPOSITORY, MAME_REVISION, ROTATIONS, calls, collapse, default_strings, drivers, expand,  # noqa: E402
                               function_macros, input_ports, number, object_macros, rom_hash, source_text,
                               split_arguments, string, strip_comments)
from mame_driver_parse import rom_sets as _rom_sets  # noqa: E402

SOURCES = {'src/mame/capcom/cps1.cpp': '986a8870ac1736120167fac2de31a98af60118ca3fe44e82c4ff02f46200c51e',
           'src/mame/capcom/cps1_v.cpp': 'f899193fb52dd715bf98f056472dc2cb88bdd79eebf6de70de1d43f61cb23115',
           'src/emu/ioport.cpp': 'd0c69fcfe5a2d8ca7d8518972f02e2f2b6576b71d6944cb3e051e54ef4a02604',
           'src/mame/capcom/kabuki.cpp': '620f5f1eafe31cef8abeca54d03dba6fbcfa6bb903d900920b4bd158e9947a6a'}
NOTICE = ('Derived from MAME src/mame/capcom/cps1.cpp and cps1_v.cpp, license BSD-3-Clause, '
          'copyright-holders: Paul Leaman; switch labels of src/emu/ioport.cpp, license BSD-3-Clause, '
          'copyright-holders: Aaron Giles; the Kabuki keys of src/mame/capcom/kabuki.cpp, license BSD-3-Clause, '
          'copyright-holders: Nicola Salmoria. See licenses/cps1-machine.md.')
OUTPUT = ROOT / 'assets/cps1-catalogue.json'
# Programmable logic dumps document the boards; they are never loaded.
PLD_REGIONS = frozenset(('aboardplds', 'bboardplds', 'cboardplds', 'dboardplds', 'plds', 'pal', 'patchpld'))
PHASE1_MACHINES = frozenset(('cps1_10MHz', 'cps1_12MHz', 'qsound'))


def rom_sets(text: str, macros: dict) -> dict:
    return _rom_sets(text, macros, PLD_REGIONS)


# The boards that join the converter in a tier of their own are listed here, and the catalogue's `tier` column says 'experimental' for them
# (never a test on a set name). None since 5 November 2026: the CPS-1.5 (QSound) boards left the experimental tier on the owner's decision
# (docs/CPS1.md), so every row is 'supported'; the column stays for the next board family that joins in a tier of its own.
EXPERIMENTAL_TIER_MACHINES = frozenset()
# The machines whose sound CPU is a Kabuki Z80: their set names an init function with the keys of the decryption.
KABUKI_MACHINES = frozenset(('qsound',))
EXCLUDED_MACHINES = {'wofhfh': 'qsound', 'forgottn': 'dial', 'pang3': 'eeprom', 'ganbare': 'timekeeper'}
GFX_TYPES = {'GFXTYPE_SPRITES': 1, 'GFXTYPE_SCROLL1': 2, 'GFXTYPE_SCROLL2': 4,
             'GFXTYPE_SCROLL3': 8, 'GFXTYPE_STARS': 16}
BOARD_FIELDS = ('id_address', 'id_value', 'mult_factor1', 'mult_factor2', 'mult_result_lo',
                'mult_result_hi', 'unknown1', 'unknown2', 'unknown3', 'layer_control',
                'priority', 'palette_control', 'layer_enable')


def boards(text: str, macros: dict) -> dict:
    result = {}
    for name in sorted(key for key in macros if re.fullmatch(r'(CPS_B_\w+|HACK_B_\d+)', key)):
        values = [number(item, macros) if not item.startswith('{') else
                  [number(part, macros) for part in split_arguments(item[1:-1])]
                  for item in split_arguments(expand(macros[name], macros))]
        if len(values) != len(BOARD_FIELDS):
            raise SystemExit('Unexpected CPS-B layout for ' + name)
        result[name] = dict(zip(BOARD_FIELDS, values))
    return result


def mappers(text: str, macros: dict) -> dict:
    result = {}
    for name, body in macros.items():
        match = re.fullmatch(r'mapper_(\w+)', name)
        if not match:
            continue
        banks = re.fullmatch(r'\{([^}]*)\},\s*(\w+)', body)
        if not banks:
            raise SystemExit('Unexpected mapper definition ' + name)
        table = re.search(r'static const struct gfx_range ' + banks.group(2) + r'\[\]\s*=\s*\{(.*?)\n\};', text, re.S)
        if not table:
            raise SystemExit('Missing mapper table ' + banks.group(2))
        ranges = []
        for row in re.findall(r'\{([^{}]*)\}', table.group(1)):
            fields = split_arguments(row)
            if fields == ['0']:
                break
            kind = 0
            for part in fields[0].split('|'):
                kind |= GFX_TYPES[part.strip()]
            ranges.append([kind] + [number(field, macros) for field in fields[1:]])
        result[match.group(1)] = {'bank_sizes': [number(v, macros) for v in split_arguments(banks.group(1))],
                                  'ranges': ranges}
    return dict(sorted(result.items()))


def configurations(raw_text: str, macros: dict) -> dict:
    """Entries come from comment-free text; MAME's line notes are kept as data."""
    pattern = r'cps1_config_table\[\]\s*=\s*\{(.*?)\n\};'
    notes = {match.group(1): match.group(2).strip() for match in re.finditer(
        r'^\s*\{\s*"(\w+)"[^\n]*?//([^\n]*)$', re.search(pattern, raw_text, re.S).group(1), re.M)}
    result = {}
    for name, body in re.findall(r'\{\s*"(\w+)"\s*,([^{}]*)\}', re.search(pattern, strip_comments(raw_text), re.S).group(1)):
        fields = [field for field in split_arguments(body) if field]
        if len(fields) < 2 or len(fields) > 6 or not fields[1].startswith('mapper_') or name in result:
            raise SystemExit('Unexpected config entry ' + name)
        extra = [number(field, macros) for field in fields[2:]] + [0] * (6 - len(fields))
        result[name] = {'board': fields[0], 'mapper': fields[1][7:], 'in2': extra[0], 'in3': extra[1],
                        'out2': extra[2], 'kludge': extra[3], 'note': notes.get(name, '')}
    return result


def support(row: dict, config: dict, kabuki: dict) -> tuple[str, str]:
    title, company = row['title'].casefold(), row['company'].casefold()
    if row['kind'] == 'cons':
        return 'excluded', 'cps_changer'
    if 'bootleg' in company or 'bootleg' in title or 'hack' in company or 'hack' in title:
        return 'excluded', 'bootleg_or_hack'
    if 'MACHINE_NOT_WORKING' in row['flags']:
        return 'excluded', 'not_working'
    if row['machine'] in EXCLUDED_MACHINES:
        return 'excluded', EXCLUDED_MACHINES[row['machine']]
    if row['machine'] not in PHASE1_MACHINES:
        return 'excluded', 'other_hardware'
    if row['init'] != 'empty_init' and not (row['machine'] in KABUKI_MACHINES and row['init'] in kabuki):
        return 'excluded', 'special_init'
    if config['board'].startswith('HACK_B_'):
        return 'excluded', 'bootleg_or_hack'
    return 'phase1', ''


def kabuki_keys(kabuki_text: str, driver_clean: str) -> dict:
    """The four numbers of each Kabuki Z80 decryption, by the driver's init function (numbers about the algorithm, no ROM data).

    `cps1_decode` decodes the first 0x8000 bytes of the sound ROM from base address 0 (checked below); each `*_decode` function
    names its keys, and each `init_*` of the driver names the `*_decode` it installs."""
    text = strip_comments(kabuki_text)
    body = re.search(r'static void cps1_decode\([^)]*\)\s*\{(.*?)\n\}', text, re.S)
    if not body or not re.search(r'kabuki_decode\(\s*src\s*,\s*dst\s*,\s*src\s*,\s*0x0000\s*,\s*0x8000\s*,\s*swap_key1', body.group(1)):
        raise SystemExit('cps1_decode of kabuki.cpp changed: check the decoded range.')
    decodes = {}
    for match in re.finditer(r'void\s+(\w+)_decode\(uint8_t \*src, uint8_t \*dst\)\s*\{\s*cps1_decode\(\s*src\s*,\s*dst\s*,'
                             r'\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*\)', text):
        decodes[match.group(1)] = [int(match.group(index), 16) for index in range(2, 6)]
    table = {}
    for match in re.finditer(r'void\s+cps_state::(init_\w+)\(\)\s*\{\s*kabuki_setup\(\s*(\w+)_decode\s*\)\s*;\s*\}', driver_clean):
        if match.group(2) not in decodes:
            raise SystemExit('No Kabuki keys for ' + match.group(2))
        keys = decodes[match.group(2)]
        table[match.group(1)] = {'swap_key1': keys[0], 'swap_key2': keys[1], 'addr_key': keys[2], 'xor_key': keys[3],
                                 'base': 0, 'length': 0x8000}
    if not table:
        raise SystemExit('No Kabuki init functions found.')
    return table


def build(cache: Path, *, offline: bool = False) -> dict:
    texts = {path: source_text(cache, path, sha, offline=offline) for path, sha in SOURCES.items()}
    driver, video = texts['src/mame/capcom/cps1.cpp'], texts['src/mame/capcom/cps1_v.cpp']
    driver_clean, video_clean = strip_comments(driver), strip_comments(video)
    driver_macros, video_macros = object_macros(driver_clean), object_macros(video_clean)
    sets, rows = rom_sets(driver_clean, driver_macros), drivers(driver_clean)
    configs = configurations(video, video_macros)
    board_table, mapper_table = boards(video_clean, video_macros), mappers(video_clean, video_macros)
    port_blocks, switch_blocks = input_ports(driver_clean, driver_macros,
                                             default_strings(texts['src/emu/ioport.cpp']))
    kabuki = kabuki_keys(texts['src/mame/capcom/kabuki.cpp'], driver_clean)
    games = []
    for row in rows:
        config = configs.get(row['set'])
        if config is None:
            raise SystemExit('No CPS-B configuration for ' + row['set'])
        if config['board'] not in board_table or config['mapper'] not in mapper_table:
            raise SystemExit('Unknown board or mapper for ' + row['set'])
        status, reason = support(row, config, kabuki)
        if status == 'phase1' and any(load.get('no_dump') for region in sets[row['set']] for load in region['loads']):
            status, reason = 'excluded', 'incomplete_dump'
        row = dict(row, support=status, reason=reason, regions=sets[row['set']],
                   tier='experimental' if row['machine'] in EXPERIMENTAL_TIER_MACHINES else 'supported', **{
            'board': config['board'], 'mapper': config['mapper'], 'ports': [config['in2'], config['in3'], config['out2']],
            'kludge': config['kludge'], 'board_note': config['note'], 'inputs': port_blocks[row['input']],
            # MAME marks guessed or undumped PAL equations in its notes.
            'mapper_verified': not re.search(r'\b(wrong|unverified|guess)', config['note'], re.I)})
        games.append(row)
    names = {game['set'] for game in games}
    if len(names) != len(games) or any(game['parent'] and game['parent'] not in names for game in games):
        raise SystemExit('Duplicate set or unknown parent.')
    for game in games:
        if game['machine'] in KABUKI_MACHINES and game['init'] not in kabuki:
            raise SystemExit('No Kabuki keys for ' + game['set'])
    return {'schema': 1, 'notice': NOTICE,
            'source': {'repository': MAME_REPOSITORY, 'revision': MAME_REVISION, 'sha256': SOURCES,
                       'license': 'BSD-3-Clause'},
            'gfx_types': {key[8:].lower(): value for key, value in GFX_TYPES.items()},
            'boards': board_table, 'mappers': mapper_table, 'kabuki': kabuki,
            'dip_blocks': {name: switch_blocks[name] for name in sorted({game['input'] for game in games})},
            'games': games}


def encode(catalogue: dict) -> bytes:
    """Stable bytes: one game per line keeps reviews of later updates readable."""
    head = {key: value for key, value in catalogue.items() if key != 'games'}
    text = json.dumps(head, sort_keys=True, separators=(',', ':'))[:-1]
    rows = ',\n'.join(json.dumps(game, sort_keys=True, separators=(',', ':')) for game in catalogue['games'])
    return (text + ',"games":[\n' + rows + '\n]}\n').encode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / '.deps' / ('mame-cps1-' + MAME_REVISION[:7]))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--offline', action='store_true', help='use only the cached pinned sources')
    args = parser.parse_args()
    data = encode(build(args.cache, offline=args.offline))
    args.output.write_bytes(data)
    print(f'{args.output}: {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}')


if __name__ == '__main__':
    main()
