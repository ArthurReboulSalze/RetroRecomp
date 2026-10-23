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
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAME_REPOSITORY = 'https://github.com/mamedev/mame'
MAME_REVISION = '61a222977fd29f22ce11fbea3f7c290fd7ced091'
SOURCES = {'src/mame/capcom/cps1.cpp': '986a8870ac1736120167fac2de31a98af60118ca3fe44e82c4ff02f46200c51e',
           'src/mame/capcom/cps1_v.cpp': 'f899193fb52dd715bf98f056472dc2cb88bdd79eebf6de70de1d43f61cb23115'}
NOTICE = ('Derived from MAME src/mame/capcom/cps1.cpp and cps1_v.cpp, license BSD-3-Clause, '
          'copyright-holders: Paul Leaman. See licenses/cps1-machine.md.')
OUTPUT = ROOT / 'assets/cps1-catalogue.json'
# Programmable logic dumps document the boards; they are never loaded.
PLD_REGIONS = frozenset(('aboardplds', 'bboardplds', 'cboardplds', 'dboardplds', 'plds', 'pal', 'patchpld'))
LOADS = {'ROM_LOAD': 'load', 'ROM_LOAD16_BYTE': 'load16_byte', 'ROM_LOAD16_WORD': 'load16_word',
         'ROM_LOAD16_WORD_SWAP': 'load16_word_swap', 'ROM_LOAD32_BYTE': 'load32_byte',
         'ROM_LOAD64_BYTE': 'load64_byte', 'ROM_LOAD64_WORD': 'load64_word'}
PHASE1_MACHINES = frozenset(('cps1_10MHz', 'cps1_12MHz'))
EXCLUDED_MACHINES = {'qsound': 'qsound', 'wofhfh': 'qsound', 'forgottn': 'dial', 'pang3': 'eeprom',
                     'ganbare': 'timekeeper'}
ROTATIONS = {'ROT0': 0, 'ROT90': 90, 'ROT180': 180, 'ROT270': 270}
GFX_TYPES = {'GFXTYPE_SPRITES': 1, 'GFXTYPE_SCROLL1': 2, 'GFXTYPE_SCROLL2': 4,
             'GFXTYPE_SCROLL3': 8, 'GFXTYPE_STARS': 16}
BOARD_FIELDS = ('id_address', 'id_value', 'mult_factor1', 'mult_factor2', 'mult_result_lo',
                'mult_result_hi', 'unknown1', 'unknown2', 'unknown3', 'layer_control',
                'priority', 'palette_control', 'layer_enable')


def source_text(cache: Path, path: str, *, offline: bool = False) -> str:
    target = cache / Path(path).name
    if not target.is_file():
        if offline:
            raise SystemExit(f'Missing pinned MAME source {target}.')
        cache.mkdir(parents=True, exist_ok=True)
        url = f'https://raw.githubusercontent.com/mamedev/mame/{MAME_REVISION}/{path}'
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise SystemExit(f'{path} exceeds the expected size.')
        target.write_bytes(data)
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCES[path]:
        raise SystemExit(f'{target} does not match the pinned MAME {MAME_REVISION[:12]} contents.')
    return data.decode('utf-8')


def strip_comments(text: str) -> str:
    """Remove C/C++ comments outside string literals, keeping line structure."""
    def replace(match):
        token = match.group(0)
        return token if token[0] in '"\'' else '\n' * token.count('\n') or ' '
    return re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*.*?\*/', replace, text, flags=re.S)


def object_macros(text: str) -> dict:
    macros = {}
    for match in re.finditer(r'^#define[ \t]+([A-Za-z_]\w*)(?![\w(])[ \t]*((?:[^\n]*\\\n)*[^\n]*)', text, re.M):
        macros[match.group(1)] = match.group(2).replace('\\\n', ' ').strip()
    return macros


def expand(text: str, macros: dict, depth: int = 0) -> str:
    if depth > 8:
        raise SystemExit('Recursive macro expansion.')
    expanded = re.sub(r'\b[A-Za-z_]\w*\b', lambda m: macros.get(m.group(0), m.group(0)), text)
    return expanded if expanded == text else expand(expanded, macros, depth + 1)


def split_arguments(text: str) -> list[str]:
    parts, depth, current, quoted = [], 0, [], False
    for index, char in enumerate(text):
        if quoted:
            current.append(char)
            if char == '"' and text[index - 1] != '\\':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '({':
            depth += 1
        elif char in ')}':
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append(''.join(current).strip()); current = []
            continue
        current.append(char)
    parts.append(''.join(current).strip())
    return parts


def calls(text: str):
    """Yield (name, arguments) for every IDENT(...) call at nesting level zero."""
    position, pattern = 0, re.compile(r'\b([A-Z][A-Z0-9_]*)\s*\(')
    while match := pattern.search(text, position):
        depth, index, quoted = 1, match.end(), False
        while depth:
            if index >= len(text):
                raise SystemExit('Unbalanced macro call ' + match.group(1))
            char = text[index]
            if quoted:
                quoted = not (char == '"' and text[index - 1] != '\\')
            elif char == '"':
                quoted = True
            else:
                depth += {'(': 1, ')': -1}.get(char, 0)
            index += 1
        yield match.group(1), text[match.end():index - 1]
        position = index


def number(text: str, macros: dict) -> int:
    value = expand(text, macros).strip()
    if not re.fullmatch(r'[0-9a-fA-Fx+*() \t-]+', value):
        raise SystemExit('Unsupported numeric expression: ' + text)
    return int(eval(value, {'__builtins__': {}}, {}))  # digits and + - * ( ) only


def string(text: str) -> str:
    if not re.fullmatch(r'"[^"\\]*"', text.strip()):
        raise SystemExit('Expected a plain string literal: ' + text)
    return text.strip()[1:-1]


def rom_hash(text: str) -> dict:
    tokens = re.sub(r'\b(CRC|SHA1)\(\s*([0-9a-fA-F]+)\s*\)', r'\1:\2', text).replace('|', ' ').split()
    result = {}
    for token in tokens:
        if token.startswith('CRC:'):
            result['crc32'] = int(token[4:], 16)
        elif token.startswith('SHA1:'):
            result['sha1'] = token[5:].lower()
        elif token in ('NO_DUMP', 'BAD_DUMP'):
            result[token.lower()] = 1
        else:
            raise SystemExit('Unsupported ROM hash or flag: ' + text)
    if not result.get('no_dump') and ('crc32' not in result or len(result.get('sha1', '')) != 40):
        raise SystemExit('Incomplete ROM hash: ' + text)
    return result


def rom_sets(text: str, macros: dict) -> dict:
    sets = {}
    for match in re.finditer(r'^ROM_START\(\s*(\w+)\s*\)(.*?)^ROM_END', text, re.S | re.M):
        name, body = match.group(1), expand(match.group(2), macros)
        regions, region = [], None
        for call, raw in calls(body):
            args = split_arguments(raw)
            if call == 'ROM_REGION':
                flags = args[2].strip()
                if flags not in ('0', 'ROMREGION_ERASEFF', 'ROMREGION_ERASE00'):
                    raise SystemExit(f'{name}: unsupported region flags {flags}')
                region = {'tag': string(args[1]), 'bytes': number(args[0], macros),
                          'erase': {'0': None, 'ROMREGION_ERASEFF': 0xff, 'ROMREGION_ERASE00': 0}[flags],
                          'loads': []}
                regions.append(region)
            elif region is None:
                raise SystemExit(f'{name}: {call} outside a region')
            elif call in LOADS:
                if len(args) != 4:
                    raise SystemExit(f'{name}: malformed {call}')
                entry = {'op': LOADS[call], 'name': string(args[0]).casefold(),
                         'offset': number(args[1], macros), 'bytes': number(args[2], macros)}
                entry.update(rom_hash(args[3]))
                region['loads'].append(entry)
            elif call in ('ROM_CONTINUE', 'ROM_RELOAD'):
                region['loads'].append({'op': call[4:].lower(), 'offset': number(args[0], macros),
                                        'bytes': number(args[1], macros)})
            elif call == 'ROM_IGNORE':
                region['loads'].append({'op': 'ignore', 'bytes': number(args[0], macros)})
            elif call == 'ROM_FILL':
                region['loads'].append({'op': 'fill', 'offset': number(args[0], macros),
                                        'bytes': number(args[1], macros), 'value': number(args[2], macros)})
            elif call == 'ROM_COPY':
                region['loads'].append({'op': 'copy', 'source': string(args[0]), 'source_offset': number(args[1], macros),
                                        'offset': number(args[2], macros), 'bytes': number(args[3], macros)})
            elif call in ('CRC', 'SHA1'):
                continue
            else:
                raise SystemExit(f'{name}: unsupported ROM macro {call}')
        sets[name] = [r for r in regions if r['tag'] not in PLD_REGIONS]
    return sets


def drivers(text: str) -> list[dict]:
    rows = []
    for kind, raw in calls(text):
        if kind not in ('GAME', 'CONS'):
            continue
        args = split_arguments(raw)
        if kind == 'GAME':
            year, name, parent, machine, inputs, _, init, rotation, company, title, flags = args
        else:
            year, name, parent, _, machine, inputs, _, init, company, title, flags = args
            rotation = 'ROT0'
        rows.append({'set': name, 'parent': '' if parent == '0' else parent, 'kind': kind.lower(),
                     'year': year, 'machine': machine, 'input': inputs, 'init': init,
                     'rotation': ROTATIONS[rotation], 'company': string(company), 'title': string(title),
                     'flags': sorted(token for token in re.split(r'[|\s]+', flags) if token)})
    return rows


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


def function_macros(text: str) -> dict:
    macros = {}
    for match in re.finditer(r'^#define[ \t]+([A-Za-z_]\w*)\(([^)]*)\)[ \t]*((?:[^\n]*\\\n)*[^\n]*)', text, re.M):
        macros[match.group(1)] = ([p.strip() for p in match.group(2).split(',') if p.strip()],
                                  match.group(3).replace('\\\n', ' '))
    return macros


IGNORED_PORT_MACROS = frozenset((
    'PORT_DIPSETTING', 'PORT_DIPLOCATION', 'PORT_NAME', 'PORT_SENSITIVITY', 'PORT_KEYDELTA',
    'PORT_CODE_INC', 'PORT_CODE_DEC', 'PORT_REMAP_TABLE', 'PORT_POSITIONS', 'PORT_CENTERDELTA',
    'PORT_WRITE_LINE_DEVICE_MEMBER', 'PORT_READ_LINE_DEVICE_MEMBER'))


def input_ports(text: str, macros: dict) -> dict:
    """Port definitions per INPUT_PORTS block: fields with masks and defaults.

    Field defaults follow MAME: active-low inputs and switches default to
    their mask, active-high ones to 0; bits no field covers read as 0.
    """
    functions = function_macros(text)
    blocks = {match.group(1): match.group(2) for match in re.finditer(
        r'INPUT_PORTS_START\(\s*(\w+)\s*\)(.*?)INPUT_PORTS_END', text, re.S)}

    def active(value):
        return {'IP_ACTIVE_LOW': None, 'IP_ACTIVE_HIGH': 0}.get(value.strip(), 'number')

    def build(name, ports, depth=0):
        if depth > 8 or name not in blocks:
            raise SystemExit('Unknown or recursive input block ' + name)
        current, field = None, None

        def add(mask, default, kind, dip):
            nonlocal field
            if current is None:
                raise SystemExit(f'{name}: field outside a port')
            ports[current] = [f for f in ports[current] if not f['mask'] & mask]
            field = {'mask': mask, 'default': default & mask, 'type': kind, 'dip': dip, 'player': 1}
            ports[current].append(field)

        def walk(body):
            nonlocal current, field
            for call, raw in calls(body):
                args = split_arguments(raw)
                if call in functions:
                    params, template = functions[call]
                    for param, value in zip(params, args):
                        template = re.sub(r'\b' + param + r'\b', value, template)
                    walk(template)
                elif call == 'PORT_INCLUDE':
                    build(args[0], ports, depth + 1)
                elif call in ('PORT_START', 'PORT_MODIFY'):
                    current, field = string(args[0]), None
                    if call == 'PORT_START' or current not in ports:
                        ports[current] = []
                elif call == 'PORT_BIT':
                    mask, level = number(args[0], macros), active(args[1])
                    default = mask if level is None else 0 if level == 0 else number(args[1], macros)
                    add(mask, default, args[2].strip().removeprefix('IPT_').lower(), False)
                elif call in ('PORT_SERVICE', 'PORT_SERVICE_DIPLOC', 'PORT_SERVICE_NO_TOGGLE'):
                    mask = number(args[0], macros)
                    add(mask, mask if active(args[1]) is None else 0, 'service', call != 'PORT_SERVICE_NO_TOGGLE')
                elif call in ('PORT_DIPNAME', 'PORT_DIPUNUSED', 'PORT_DIPUNUSED_DIPLOC',
                              'PORT_DIPUNKNOWN', 'PORT_DIPUNKNOWN_DIPLOC'):
                    add(number(args[0], macros), number(args[1], macros), 'dip', True)
                elif call == 'PORT_CONDITION':
                    if field is None or args[2].strip() not in ('EQUALS', 'NOTEQUALS'):
                        raise SystemExit(f'{name}: unsupported condition {raw}')
                    field['condition'] = [string(args[0]), number(args[1], macros),
                                          args[2].strip() == 'EQUALS', number(args[3], macros)]
                elif call == 'PORT_PLAYER':
                    field['player'] = number(args[0], macros)
                elif call not in IGNORED_PORT_MACROS:
                    raise SystemExit(f'{name}: unsupported input macro {call}')
        walk(blocks[name])
        return ports

    result = {}
    for name in blocks:
        ports = build(name, {})
        defaults = {port: 0 for port in ports}
        for conditional in (False, True):
            for port, fields in ports.items():
                for field in fields:
                    if bool(field.get('condition')) != conditional:
                        continue
                    if conditional:
                        tag, mask, equals, value = field['condition']
                        if ((defaults.get(tag, 0) & mask) == value) != equals:
                            continue
                    defaults[port] = (defaults[port] & ~field['mask']) | field['default']
        result[name] = {port: {'default': defaults[port],
                               'inputs': sorted([f['mask'], f['type'], f['player']] for f in fields
                                                if not f['dip'] and f['type'] not in ('unknown', 'unused')),
                               'switches': sorted([f['mask'], f['default']] + ([f['condition']] if f.get('condition') else [])
                                                  for f in fields if f['dip'])}
                        for port, fields in ports.items()}
    return result


def support(row: dict, config: dict) -> tuple[str, str]:
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
    if row['init'] != 'empty_init':
        return 'excluded', 'special_init'
    if config['board'].startswith('HACK_B_'):
        return 'excluded', 'bootleg_or_hack'
    return 'phase1', ''


def build(cache: Path, *, offline: bool = False) -> dict:
    texts = {path: source_text(cache, path, offline=offline) for path in SOURCES}
    driver, video = texts['src/mame/capcom/cps1.cpp'], texts['src/mame/capcom/cps1_v.cpp']
    driver_clean, video_clean = strip_comments(driver), strip_comments(video)
    driver_macros, video_macros = object_macros(driver_clean), object_macros(video_clean)
    sets, rows = rom_sets(driver_clean, driver_macros), drivers(driver_clean)
    configs = configurations(video, video_macros)
    board_table, mapper_table = boards(video_clean, video_macros), mappers(video_clean, video_macros)
    port_blocks = input_ports(driver_clean, driver_macros)
    games = []
    for row in rows:
        config = configs.get(row['set'])
        if config is None:
            raise SystemExit('No CPS-B configuration for ' + row['set'])
        if config['board'] not in board_table or config['mapper'] not in mapper_table:
            raise SystemExit('Unknown board or mapper for ' + row['set'])
        status, reason = support(row, config)
        if status == 'phase1' and any(load.get('no_dump') for region in sets[row['set']] for load in region['loads']):
            status, reason = 'excluded', 'incomplete_dump'
        row = dict(row, support=status, reason=reason, regions=sets[row['set']], **{
            'board': config['board'], 'mapper': config['mapper'], 'ports': [config['in2'], config['in3'], config['out2']],
            'kludge': config['kludge'], 'board_note': config['note'], 'inputs': port_blocks[row['input']],
            # MAME marks guessed or undumped PAL equations in its notes.
            'mapper_verified': not re.search(r'\b(wrong|unverified|guess)', config['note'], re.I)})
        games.append(row)
    names = {game['set'] for game in games}
    if len(names) != len(games) or any(game['parent'] and game['parent'] not in names for game in games):
        raise SystemExit('Duplicate set or unknown parent.')
    return {'schema': 1, 'notice': NOTICE,
            'source': {'repository': MAME_REPOSITORY, 'revision': MAME_REVISION, 'sha256': SOURCES,
                       'license': 'BSD-3-Clause'},
            'gfx_types': {key[8:].lower(): value for key, value in GFX_TYPES.items()},
            'boards': board_table, 'mappers': mapper_table, 'games': games}


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
