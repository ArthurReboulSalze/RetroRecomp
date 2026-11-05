"""Build the ROM-free CPS-2 catalogue from pinned MAME driver sources.

Development tool only: the converter reads the generated JSON, never MAME. The driver `cps2.cpp` is BSD-3-Clause (copyright-holders:
Paul Leaman, Andreas Naive, Nicola Salmoria); the catalogue keeps its revision, hashes and notice. The generic reading of MAME sources is
shared with tools/build_cps1_catalogue.py (tools/mame_driver_parse.py). The CPS-B board and the graphics mapper of the CPS-2 are the ones
of the CPS-1 catalogue (named here, not copied). Keys are never in this file: MAME keeps each game's 20-byte key in a `key` ROM region
that the player's own romset zip carries; only the file's name, size and hashes are recorded so that the key a player supplies can be
recognised. Unknown ROM macros, hash flags or input macros stop the build instead of being guessed.
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

from mame_driver_parse import (MAME_REPOSITORY, MAME_REVISION, default_strings, drivers, input_ports, object_macros,  # noqa: E402
                               rom_sets, source_text, strip_comments)

SOURCES = {'src/mame/capcom/cps2.cpp': 'e095894df35d60c83e8626f4c56b00d4304d6604947369768cfacb03ab3e6515',
           'src/mame/capcom/cps1_v.cpp': 'f899193fb52dd715bf98f056472dc2cb88bdd79eebf6de70de1d43f61cb23115',
           'src/emu/ioport.cpp': 'd0c69fcfe5a2d8ca7d8518972f02e2f2b6576b71d6944cb3e051e54ef4a02604'}
NOTICE = ('Derived from MAME src/mame/capcom/cps2.cpp, license BSD-3-Clause, copyright-holders: Paul Leaman, Andreas Naive, '
          'Nicola Salmoria; the CPS-B board and the graphics mapper named here are those of src/mame/capcom/cps1_v.cpp '
          '(copyright-holders: Paul Leaman); switch labels of src/emu/ioport.cpp, license BSD-3-Clause, copyright-holders: Aaron Giles. '
          'The file holds no encryption key. See licenses/cps1-machine.md.')
OUTPUT = ROOT / 'assets/cps2-catalogue.json'
# the first scope: the standard A-board with a battery-backed key (docs/CPS2.md); the other machines of the driver are named refusals
PHASE1_MACHINES = frozenset(('cps2',))
EXCLUDED_MACHINES = {'dead_cps2': 'dead_board', 'dead_cps2comm': 'dead_board', 'cps2comm': 'network_adapter', 'gigaman2': 'other_hardware'}
# initialisers that need an input the first scope has not got (spinners, paddles) or a board variant (single board)
SPECIAL_INITS = frozenset(('init_ecofghtr', 'init_pzloop2', 'init_singbrd'))
BOARD, MAPPER = 'CPS_B_21_DEF', 'cps2'


def support(row: dict) -> tuple[str, str]:
    title, company = row['title'].casefold(), row['company'].casefold()
    if 'bootleg' in company or 'bootleg' in title or 'hack' in company or 'hack' in title:
        return 'excluded', 'bootleg_or_hack'
    if 'MACHINE_NOT_WORKING' in row['flags']:
        return 'excluded', 'not_working'
    if row['machine'] in EXCLUDED_MACHINES:
        return 'excluded', EXCLUDED_MACHINES[row['machine']]
    if row['machine'] not in PHASE1_MACHINES:
        return 'excluded', 'other_hardware'
    if row['init'] in SPECIAL_INITS:
        return 'excluded', 'special_init'
    return 'phase1', ''


def build(cache: Path, *, offline: bool = False) -> dict:
    texts = {path: source_text(cache, path, sha, offline=offline) for path, sha in SOURCES.items()}
    driver = strip_comments(texts['src/mame/capcom/cps2.cpp'])
    macros = object_macros(driver)
    video = strip_comments(texts['src/mame/capcom/cps1_v.cpp'])
    if not re.search(r'\{\s*"cps2"\s*,\s*' + BOARD + r'\s*,\s*mapper_cps2\s*\}', video) \
            and not re.search(r'\{"cps2",\s+' + BOARD + r',\s+mapper_cps2\s*\}', video):
        raise SystemExit('The CPS-2 board configuration of cps1_v.cpp changed: check ' + BOARD + ' and mapper_cps2.')
    sets, rows = rom_sets(driver, macros), drivers(driver)
    ports, _ = input_ports(driver, macros, default_strings(texts['src/emu/ioport.cpp']))
    games = []
    for row in rows:
        regions = sets[row['set']]
        keys = [region for region in regions if region['tag'] == 'key']
        loads = [load for region in keys for load in region['loads'] if load['op'] == 'load']
        if row['machine'] != 'gigaman2' and (len(loads) != 1 or loads[0]['bytes'] != 0x14):
            raise SystemExit(f"{row['set']}: expected one 20-byte key file")
        status, reason = support(row)
        if status == 'phase1' and any(load.get('no_dump') for region in regions for load in region['loads']):
            status, reason = 'excluded', 'incomplete_dump'
        games.append(dict(row, support=status, reason=reason, regions=regions, board=BOARD, mapper=MAPPER,
                          inputs=ports[row['input']]))
    names = {game['set'] for game in games}
    if len(names) != len(games):
        raise SystemExit('Duplicate set.')
    # a parent named in the driver but defined elsewhere (a CPS-1 or bootleg parent) is kept as written
    return {'schema': 1, 'notice': NOTICE,
            'source': {'repository': MAME_REPOSITORY, 'revision': MAME_REVISION, 'sha256': SOURCES, 'license': 'BSD-3-Clause'},
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
