"""Assemble a CPS-1 set's memory regions and board description for the runtime.

Load operations follow MAME's ROM loader: grouped and skipped writes,
reversed word groups, CONTINUE/RELOAD/IGNORE on the same file, FILL and COPY
processed in definition order. Regions hold logical byte order (the 68000
program region is big-endian as addressed). Nothing is written beside ROMs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from zipfile import ZipFile

from . import cps1_catalogue

# (group size, skip, reversed) per load operation.
LAYOUTS = {'load': (1, 0, False), 'load16_byte': (1, 1, False), 'load16_word': (1, 0, False),
           'load16_word_swap': (2, 0, True), 'load32_byte': (1, 3, False),
           'load64_byte': (1, 7, False), 'load64_word': (2, 6, False)}
RUNTIME_REGIONS = ('maincpu', 'audiocpu', 'gfx', 'oki', 'stars')
PORTS = ('IN0', 'IN1', 'IN2', 'IN3', 'DSWA', 'DSWB', 'DSWC')


def member_bytes(game_set) -> dict:
    """Re-read the identified members; contents must still match the identity."""
    data = {}
    for member in game_set.members:
        with ZipFile(member['archive']) as archive:
            payload = archive.read(member['archive_path'])
        if hashlib.sha256(payload).hexdigest() != member['sha256']:
            raise ValueError('CPS-1 ROM ' + member['name'] + ' changed after identification.')
        data[member['name']] = payload
    return data


def _write(region: bytearray, offset: int, payload: bytes, layout: tuple, tag: str, name: str):
    group, skip, reverse = layout
    count = (len(payload) + group - 1) // group
    if offset + count * group + (count - 1) * skip > len(region):
        raise ValueError(f'CPS-1 ROM {name} does not fit region {tag}.')
    if skip == 0 and not reverse:
        region[offset:offset + len(payload)] = payload
        return
    position = offset
    for start in range(0, len(payload), group):
        chunk = payload[start:start + group]
        if reverse:
            for index, value in enumerate(chunk):
                region[position + group - 1 - index] = value
        else:
            region[position:position + len(chunk)] = chunk
        position += group + skip


def assemble(game: dict, files: dict) -> dict:
    regions = {}
    for spec in game['regions']:
        tag = spec['tag']
        region = regions[tag] = bytearray([spec['erase'] or 0]) * spec['bytes']
        payload, cursor, layout, name = None, 0, None, ''
        for load in spec['loads']:
            op = load['op']
            if op in LAYOUTS:
                if load.get('no_dump'):
                    payload, name = None, load['name']
                    continue
                payload, name, layout = files[load['name']], load['name'], LAYOUTS[op]
                part, cursor = payload[:load['bytes']], load['bytes']
                _write(region, load['offset'], part, layout, tag, name)
            elif op in ('continue', 'reload', 'ignore'):
                if payload is None:
                    continue
                if op == 'reload':
                    cursor = 0
                if op == 'ignore':
                    cursor += load['bytes']
                    continue
                part = payload[cursor:cursor + load['bytes']]
                if len(part) != load['bytes']:
                    raise ValueError(f'CPS-1 ROM {name} is shorter than its layout.')
                _write(region, load['offset'], part, layout, tag, name)
                cursor += load['bytes']
            elif op == 'fill':
                region[load['offset']:load['offset'] + load['bytes']] = bytes([load['value'] & 0xff]) * load['bytes']
            elif op == 'copy':
                source = regions[load['source']]
                region[load['offset']:load['offset'] + load['bytes']] = \
                    source[load['source_offset']:load['source_offset'] + load['bytes']]
            else:
                raise ValueError('Unknown CPS-1 load operation ' + op)
    return regions


def descriptor(game: dict) -> str:
    """Plain key/value text read by the C runtime (no JSON parser there)."""
    data = cps1_catalogue.catalogue()
    board, mapper = data['boards'][game['board']], data['mappers'][game['mapper']]
    clock = 12000000 if game['machine'] == 'cps1_12MHz' else 10000000
    lines = ['cps1-board 1', 'set ' + game['set'], f'cpu_clock {clock}',
             f'id {board["id_address"]} {board["id_value"]}',
             'mult {} {} {} {}'.format(board['mult_factor1'], board['mult_factor2'],
                                        board['mult_result_lo'], board['mult_result_hi']),
             f'layer_control {board["layer_control"]}',
             'priority ' + ' '.join(map(str, board['priority'])),
             f'palette_control {board["palette_control"]}',
             'layer_enable ' + ' '.join(map(str, board['layer_enable'])),
             'bank_sizes ' + ' '.join(map(str, mapper['bank_sizes'])),
             'ports ' + ' '.join(map(str, game['ports'])), f'kludge {game["kludge"]}',
             f'rotation {game["rotation"]}']
    lines += ['range ' + ' '.join(map(str, row)) for row in mapper['ranges']]
    for port in PORTS:
        if port in game['inputs']:
            lines.append(f'input {port} {game["inputs"][port]["default"]}')
    return '\n'.join(lines) + '\n'


def write_board(directory: Path, game_set, game: dict | None = None) -> dict:
    game = game or cps1_catalogue.by_set()[game_set.set_name]
    regions = assemble(game, member_bytes(game_set))
    directory.mkdir(parents=True, exist_ok=True)
    written = {}
    for tag in RUNTIME_REGIONS:
        if tag in regions:
            path = directory / (tag + '.bin')
            path.write_bytes(bytes(regions[tag]))
            written[tag] = path
    (directory / 'board.txt').write_text(descriptor(game), encoding='ascii', newline='\n')
    written['board'] = directory / 'board.txt'
    return written
