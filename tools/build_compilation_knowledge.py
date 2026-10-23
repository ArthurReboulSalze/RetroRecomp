"""Build a ROM-free hint resource from successful local conversion evidence.

Only an explicit input directory is scanned. Sources are read, never modified.
Failed exports and private logs/configuration are not copied into the resource.
"""
from pathlib import Path
import argparse
from datetime import datetime
import gzip
import hashlib
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.batch import identify
from smsrecomp.knowledge import RESOURCE, FIELDS, MAX_BYTES, load, validate_payload
from smsrecomp.knowledge_build import (build_record, compact_snes, compact_spc_refs, engines as current_engines,
                                       qualified_reports)
from smsrecomp.systems import get_profile


def build(roms, *, reports: Path, output: Path, base: Path | None = None) -> dict:
    engines = current_engines()
    # A collection may be regenerated one console at a time, or its old
    # reports deleted. Keep previously qualified hints from the supplied
    # snapshot; new observations still need their normal qualification gate.
    consoles = {system: {} for system in engines}
    if base is not None:
        for system, records in load(base)['consoles'].items():
            consoles.setdefault(system,{}).update(records)
    retained = {system: set(records) for system, records in consoles.items()}
    refreshed = {system: set() for system in engines}
    qualified = qualified_reports(reports.glob('*/datas/reports/*/conversion-report.json'))
    seen = set()
    omitted = {'unqualified': 0, 'ram_without_rom_source': 0}
    for path in roms:
        item = identify(path)
        key = (item.system, item.sha256)
        if item.error or item.system not in engines or key in seen:
            continue
        seen.add(key)
        rom = get_profile(item.system).read_rom(path)
        record = build_record(rom, item.system, qualified.get(key), engines[item.system], omitted)
        if record is None:
            continue
        consoles[item.system][rom.sha256] = record
        refreshed[item.system].add(rom.sha256)
    for record in consoles.get('snes', {}).values():
        compact_snes(record)
    payload = validate_payload({'schema': 1, 'consoles': consoles})
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('ascii')
    if len(raw) > MAX_BYTES: raise ValueError('Knowledge size budget exceeded.')
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    temporary.write_bytes(packed);temporary.replace(output)
    load.cache_clear()
    return {'rom_free': True, 'raw_bytes': len(raw), 'compressed_bytes': len(packed),
            'sha256': hashlib.sha256(packed).hexdigest(), 'omitted': omitted,
            'refresh': {system: {
                'retained': len(retained[system] - refreshed[system]),
                'requalified': len(retained[system] & refreshed[system]),
                'added': len(refreshed[system] - retained[system])}
                for system in engines},
            'consoles': {system: {'games': len(games),
                'entries': sum(sum(len(r.get(f, [])) for f in FIELDS[system]) for r in games.values())}
                for system,games in consoles.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', action='append', type=Path, required=True)
    parser.add_argument('--reports', type=Path, default=ROOT/'Export/Games')
    parser.add_argument('--output', type=Path, default=ROOT/RESOURCE)
    parser.add_argument('--base', type=Path,
        help='Previously qualified ROM-free snapshot to retain when refreshing a partial collection.')
    args = parser.parse_args()
    suffixes = {'.zip','.sms','.gg','.gb','.nes','.bin','.rom','.sfc','.smc','.md','.gen'}
    paths = sorted({p for folder in args.rom_dir for p in folder.rglob('*')
                    if p.is_file() and p.suffix.casefold() in suffixes})
    print(json.dumps(build(paths,reports=args.reports,output=args.output,base=args.base),indent=2))

if __name__ == '__main__':
    main()
