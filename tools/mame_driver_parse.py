"""Generic reading of MAME driver sources, shared by the catalogue builders of the Capcom boards.

Development tools only: the converter reads the generated JSON, never MAME. Used by tools/build_cps1_catalogue.py (CPS-1 and
CPS-1.5) and tools/build_cps2_catalogue.py (CPS-2). The MAME drivers are BSD-3-Clause (copyright-holders named in
licenses/cps1-machine.md). Unknown ROM macros, hash flags or input macros stop the build instead of being guessed.
"""
import hashlib
from pathlib import Path
import re
import urllib.request

MAME_REPOSITORY = 'https://github.com/mamedev/mame'
MAME_REVISION = '61a222977fd29f22ce11fbea3f7c290fd7ced091'
LOADS = {'ROM_LOAD': 'load', 'ROM_LOAD16_BYTE': 'load16_byte', 'ROM_LOAD16_WORD': 'load16_word',
         'ROM_LOAD16_WORD_SWAP': 'load16_word_swap', 'ROM_LOAD32_BYTE': 'load32_byte',
         'ROM_LOAD64_BYTE': 'load64_byte', 'ROM_LOAD64_WORD': 'load64_word'}
REGION_CALLS = ('ROM_REGION', 'ROM_REGION16_BE', 'ROM_REGION16_LE')
ROTATIONS = {'ROT0': 0, 'ROT90': 90, 'ROT180': 180, 'ROT270': 270}


def source_text(cache: Path, path: str, sha256: str, *, offline: bool = False) -> str:
    """One pinned MAME source file: read from the cache, or fetched once at the pinned revision; its SHA-256 must match."""
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
    if hashlib.sha256(data).hexdigest() != sha256:
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


def rom_sets(text: str, macros: dict, ignored_regions=frozenset()) -> dict:
    """The regions and loads of every ROM_START block; regions named in `ignored_regions` (programmable logic dumps) are dropped."""
    sets = {}
    for match in re.finditer(r'^ROM_START\(\s*(\w+)\s*\)(.*?)^ROM_END', text, re.S | re.M):
        name, body = match.group(1), expand(match.group(2), macros)
        regions, region = [], None
        for call, raw in calls(body):
            args = split_arguments(raw)
            if call in REGION_CALLS:
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
        sets[name] = [r for r in regions if r['tag'] not in ignored_regions]
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


def function_macros(text: str) -> dict:
    macros = {}
    for match in re.finditer(r'^#define[ \t]+([A-Za-z_]\w*)\(([^)]*)\)[ \t]*((?:[^\n]*\\\n)*[^\n]*)', text, re.M):
        macros[match.group(1)] = ([p.strip() for p in match.group(2).split(',') if p.strip()],
                                  match.group(3).replace('\\\n', ' '))
    return macros


IGNORED_PORT_MACROS = frozenset((
    'PORT_DIPLOCATION', 'PORT_NAME', 'PORT_SENSITIVITY', 'PORT_KEYDELTA',
    'PORT_CODE_INC', 'PORT_CODE_DEC', 'PORT_REMAP_TABLE', 'PORT_POSITIONS', 'PORT_CENTERDELTA',
    'PORT_WRITE_LINE_DEVICE_MEMBER', 'PORT_READ_LINE_DEVICE_MEMBER'))


def default_strings(text: str) -> dict:
    """MAME's DEF_STR labels (input_port_default_strings of ioport.cpp)."""
    table = dict(re.findall(r'\{\s*INPUT_STRING_(\w+)\s*,\s*"([^"\\]*)"\s*\}', text))
    if len(table) < 100:
        raise SystemExit('MAME default input strings not found.')
    return table


def collapse(fields: list) -> list:
    """MAME's ioport_port::insert_field, in definition order: a field drops the
    earlier fields it overlaps when either has no condition or both share one
    (switches under different conditions coexist); unknown and unused bits are
    only narrowed."""
    kept = []
    for new in fields:
        survivors = []
        for old in kept:
            if old['mask'] & new['mask'] and (not new.get('condition') or not old.get('condition')
                                              or old.get('condition') == new.get('condition')):
                if old['type'] in ('unknown', 'unused') and old['mask'] & ~new['mask']:
                    old = dict(old, mask=old['mask'] & ~new['mask'], default=old['default'] & ~new['mask'])
                else:
                    continue
            survivors.append(old)
        kept = survivors + [new]
    return kept


def input_ports(text: str, macros: dict, strings: dict) -> dict:
    """Port definitions per INPUT_PORTS block: fields with masks and defaults,
    and the named DIP switches with their settings.

    Field defaults follow MAME: active-low inputs and switches default to
    their mask, active-high ones to 0; bits no field covers read as 0.
    """
    functions = function_macros(text)
    blocks = {match.group(1): match.group(2) for match in re.finditer(
        r'INPUT_PORTS_START\(\s*(\w+)\s*\)(.*?)INPUT_PORTS_END', text, re.S)}

    def active(value):
        return {'IP_ACTIVE_LOW': None, 'IP_ACTIVE_HIGH': 0}.get(value.strip(), 'number')

    def label(text):
        match = re.fullmatch(r'DEF_STR\s*\(\s*(\w+)\s*\)', text.strip())
        value = strings.get(match.group(1)) if match else string(text)
        if value is None or not value.isascii():
            raise SystemExit('Unsupported switch label: ' + text)
        return value

    def build(name, ports, depth=0):
        if depth > 8 or name not in blocks:
            raise SystemExit('Unknown or recursive input block ' + name)
        current, field = None, None

        def add(mask, default, kind, dip, title=None):
            nonlocal field
            if current is None:
                raise SystemExit(f'{name}: field outside a port')
            field = {'mask': mask, 'default': default & mask, 'type': kind, 'dip': dip, 'player': 1,
                     'name': title, 'settings': []}
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
                elif call in ('PORT_DIPNAME', 'PORT_CONFNAME'):
                    add(number(args[0], macros), number(args[1], macros), 'dip', True, label(args[2]))
                elif call in ('PORT_DIPUNUSED', 'PORT_DIPUNUSED_DIPLOC', 'PORT_DIPUNKNOWN', 'PORT_DIPUNKNOWN_DIPLOC'):
                    add(number(args[0], macros), number(args[1], macros), 'dip', True)
                elif call in ('PORT_DIPSETTING', 'PORT_CONFSETTING'):
                    if field is None or field['type'] != 'dip':
                        raise SystemExit(f'{name}: setting outside a switch {raw}')
                    field['settings'].append([number(args[0], macros), label(args[1])])
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

    result, switches = {}, {}
    for name in blocks:
        ports = {port: collapse(fields) for port, fields in build(name, {}).items()}
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
        # Named switches the player may set, by port as MAME lists them (DSWA,
        # DSWB, DSWC) then in definition order; unused, unknown and service
        # switches stay at their defaults.
        switches[name] = [
            {'port': port, 'mask': f['mask'], 'default': f['default'], 'name': f['name'], 'settings': f['settings'],
             **({'condition': f['condition']} if f.get('condition') else {})}
            for port, fields in sorted(ports.items()) for f in fields
            if f['type'] == 'dip' and f['name'] not in (None, strings['Unused'], strings['Unknown'])
            and len(f['settings']) > 1]
    return result, switches
