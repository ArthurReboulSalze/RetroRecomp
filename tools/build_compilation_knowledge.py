"""Build a ROM-free hint resource from successful local conversion evidence.

Only an explicit input directory is scanned. Sources are read, never modified.
Failed exports and private logs/configuration are not copied into the resource.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp import core, gameboy, nes, megadrive, megadrive_z80, supernintendo, snes_spc
from smsrecomp.batch import identify
from smsrecomp.console16 import REPOSITORIES
from smsrecomp.knowledge import RESOURCE, FIELDS, validate_payload
from smsrecomp.library import GameMemory, library_root, read_code_patterns
from smsrecomp.gameboy_coverage import read_entries
from smsrecomp.systems import get_profile


def build(roms, *, reports: Path, output: Path) -> dict:
    engines = {'sms': core.ENGINE_REV, 'gg': core.ENGINE_REV, 'gb': gameboy.ENGINE_REV,
               'nes': nes.ENGINE_REV, 'md': REPOSITORIES['md'][1], 'snes': REPOSITORIES['snes'][1]}
    consoles = {system: {} for system in engines}
    qualified = {}
    for path in reports.glob('*/datas/reports/*/conversion-report.json'):
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            if report.get('native_validation', {}).get('passed'):
                qualified[(report['system']['id'], report['rom']['sha256'])] = report
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    seen = set()
    omitted = {'unqualified': 0, 'ram_without_rom_source': 0}
    for path in roms:
        item = identify(path)
        key = (item.system, item.sha256)
        if item.error or item.system not in consoles or key in seen:
            continue
        seen.add(key)
        rom = get_profile(item.system).read_rom(path)
        record = {'engine': engines[item.system], 'rom_bytes': len(rom.data)}
        if item.system in ('sms', 'gg'):
            memory = GameMemory(rom, library_root(item.system))
            metadata = memory.metadata()
            generations = metadata.get('generations', [])
            if not (generations and generations[-1].get('engine_revision') == engines[item.system]
                    and generations[-1].get('reference_vdp_trace_match') is True
                    and all(c.get('passed') for c in generations[-1].get('checks', []))):
                omitted['unqualified'] += 1; continue
            record['rom_entries'] = [list(e) for e in sorted(memory.seeds())]
            refs = {rom.data.find(raw) for raw in read_code_patterns(memory.code_journal)}
            record['pattern_refs'] = [[offset] for offset in sorted(refs) if offset >= 0]
        else:
            report = qualified.get(key)
            expected_engine = supernintendo.knowledge_engine(rom) if item.system == 'snes' else engines[item.system]
            if not report or report.get('compiler', {}).get('revision') != expected_engine:
                omitted['unqualified'] += 1; continue
            record['engine'] = expected_engine
            if item.system == 'gb':
                record['rom_entries'] = [list(e) for e in sorted(read_entries(gameboy._verified_trace(rom), len(rom.data)))]
            elif item.system == 'nes':
                directory = library_root('nes') / rom.sha256 / nes.ENGINE_REV
                record['rom_entries'] = [[int(bank,16),int(pc,16)] for _,bank,pc in
                    (e.split(':') for e in sorted(nes._seed_sites(directory/'cycle-seeds.trace')))]
            else:
                if item.system == 'md':
                    record['rom_entries'] = [[addr] for addr in sorted(megadrive.read_entries(rom))]
                    variants = megadrive.read_ram_variants(rom)
                else:
                    variants = supernintendo.read_ram_variants(rom)
                refs = []
                for variant in variants:
                    raw = bytes.fromhex(variant['bytes']); offset = rom.data.find(raw)
                    if offset >= 0: refs.append([variant['address'], offset, len(raw)])
                    else: omitted['ram_without_rom_source'] += 1
                record['ram_refs'] = refs
                if item.system == 'snes':
                    offsets = {op: rom.data.find(bytes([op])) for op in range(256)}
                    masks = snes_spc.read_masks(rom)
                    refs = []
                    for pc in range(65536):
                        bits = int.from_bytes(masks[pc*32:(pc+1)*32], 'little')
                        while bits:
                            bit = bits & -bits; op = bit.bit_length()-1; bits ^= bit
                            if offsets[op] >= 0: refs.append([pc, offsets[op]])
                    record['spc_refs'] = refs[:FIELDS['snes']['spc_refs'][1]]
                if item.system == 'md':
                    # Z80 operands are live. Match only structural opcode bytes
                    # against the user's ROM; do not ship a driver image.
                    cache, refs = {}, []
                    for pc, mask, text in megadrive_z80.normalize(megadrive_z80.read_variants(rom)):
                        raw = bytes.fromhex(text); key = (mask, raw)
                        if key not in cache:
                            offset = rom.data.find(raw[:1])
                            while offset >= 0:
                                if offset+4 <= len(rom.data) and all(
                                    not mask & (1<<i) or rom.data[offset+i] == raw[i] for i in range(4)): break
                                offset = rom.data.find(raw[:1], offset+1)
                            cache[key] = offset
                        offset = cache[key]
                        if offset >= 0: refs.append([pc, offset, 4])
                        else: omitted['ram_without_rom_source'] += 1
                    record['z80_refs'] = refs
        consoles[item.system][rom.sha256] = record
    payload = validate_payload({'schema': 1, 'consoles': consoles})
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('ascii')
    if len(raw) > 32*1024*1024: raise ValueError('Knowledge size budget exceeded.')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    temporary.write_bytes(packed);temporary.replace(output)
    return {'rom_free': True, 'raw_bytes': len(raw), 'compressed_bytes': len(packed),
            'sha256': hashlib.sha256(packed).hexdigest(), 'omitted': omitted,
            'consoles': {system: {'games': len(games),
                'entries': sum(sum(len(r.get(f, [])) for f in FIELDS[system]) for r in games.values())}
                for system,games in consoles.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', action='append', type=Path, required=True)
    parser.add_argument('--reports', type=Path, default=ROOT/'Export/Games')
    parser.add_argument('--output', type=Path, default=ROOT/RESOURCE)
    args = parser.parse_args()
    suffixes = {'.zip','.sms','.gg','.gb','.nes','.bin','.rom','.sfc','.smc','.md','.gen'}
    paths = sorted({p for folder in args.rom_dir for p in folder.rglob('*')
                    if p.is_file() and p.suffix.casefold() in suffixes})
    print(json.dumps(build(paths,reports=args.reports,output=args.output),indent=2))

if __name__ == '__main__':
    main()
