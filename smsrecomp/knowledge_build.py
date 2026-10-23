"""Qualified, ROM-free hint records built from local conversion evidence.

Shared by the bundled-snapshot tool and the converter's knowledge export.
A record is only built for an exact ROM whose latest conversion passed its
native validation with the current compiler; its journals must not have
grown since. Sources are read, never modified, and no ROM byte is copied.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .knowledge import FIELDS
from .library import GameMemory, library_root

# Consoles whose local learning can become shared records. Neo Geo uses its
# own firmware-scoped builder; X68000 and CPS-1 observations stay private.
SYSTEMS = ('sms', 'gg', 'gb', 'nes', 'md', 'snes')


def engines() -> dict:
    from . import core, gameboy, nes
    from .console16 import REPOSITORIES
    return {'sms': core.ENGINE_REV, 'gg': core.ENGINE_REV, 'gb': gameboy.ENGINE_REV,
            'nes': nes.ENGINE_REV, 'md': REPOSITORIES['md'][1], 'snes': REPOSITORIES['snes'][1]}


def observations_qualified(paths, report: dict) -> bool:
    """Do not promote observations appended after the last successful run."""
    try:
        qualified_at = datetime.fromisoformat(report['created_utc']).timestamp()
        return all(not path.exists() or path.stat().st_mtime <= qualified_at
                   for path in paths)
    except (KeyError, OSError, TypeError, ValueError):
        return False


def journals_qualified(memory, report: dict) -> bool:
    return observations_qualified((memory.journal, memory.code_journal), report)


def compact_spc_refs(refs):
    by_offset = {}
    for pc, offset in refs:
        by_offset.setdefault(offset, set()).add(pc)
    result = []
    for offset, positions in sorted(by_offset.items()):
        first = last = None
        for pc in sorted(positions):
            if last is not None and pc == last + 1:
                last = pc
            else:
                if last is not None: result.append([first,last,offset])
                first = last = pc
        if last is not None: result.append([first,last,offset])
    return result


def qualified_reports(paths) -> dict:
    """The newest natively validated report of each exact identity."""
    qualified = {}
    for path in paths:
        try:
            report = json.loads(Path(path).read_text(encoding='utf-8'))
            if report.get('native_validation', {}).get('passed'):
                key = (report['system']['id'], report['rom']['sha256'])
                previous = qualified.get(key, {})
                if report.get('created_utc', '') >= previous.get('created_utc', ''):
                    qualified[key] = report
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return qualified


def build_record(rom, system: str, report: dict | None, engine: str, omitted: dict) -> dict | None:
    """One identity's record, or None (counted in `omitted`) when unqualified."""
    from . import megadrive, megadrive_z80, nes, supernintendo, snes_spc, gameboy
    from .gameboy_coverage import read_entries
    record = {'engine': engine, 'rom_bytes': len(rom.data)}
    if system in ('sms', 'gg'):
        memory = GameMemory(rom, library_root(system))
        metadata = memory.metadata()
        generations = metadata.get('generations', [])
        # Probe journals are additive, including observations made during
        # a later failed conversion. Old metadata alone must not qualify
        # their current contents for a new shared snapshot.
        if not (report and report.get('engine_revision') == engine
                and report.get('backend') == 'banked'
                and generations and generations[-1].get('checks')
                and generations[-1].get('created_utc') == report.get('created_utc')
                and generations[-1].get('engine_revision') == engine
                and generations[-1].get('reference_vdp_trace_match') is True
                and all(c.get('passed') for c in generations[-1].get('checks', []))
                and journals_qualified(memory, report)):
            omitted['unqualified'] += 1; return None
        record['rom_entries'] = [list(e) for e in sorted(memory.seeds())]
        # The conversion used both bundled and local byte-checked windows.
        # Keep that qualified union; reading only the private journal would
        # silently drop shared windows that needed no new fallback.
        offsets = [rom.data.find(raw) for raw in memory.code_patterns()]
        omitted['ram_without_rom_source'] += sum(offset < 0 for offset in offsets)
        record['pattern_refs'] = [[offset] for offset in sorted(set(offsets)) if offset >= 0]
        return record
    expected_engine = supernintendo.knowledge_engine(rom) if system == 'snes' else engine
    if not report or report.get('compiler', {}).get('revision') != expected_engine:
        omitted['unqualified'] += 1; return None
    if system == 'md' and not observations_qualified(
            (megadrive.memory_file(rom), megadrive_z80.memory_file(rom)), report):
        # A later failed or unfinished replay may extend either CPU's
        # private hints while leaving the previous export/report intact.
        # Keep the old shared record until the new union is qualified.
        omitted['unqualified'] += 1; return None
    if system == 'nes' and not observations_qualified(
            (library_root('nes') / rom.sha256 / nes.ENGINE_REV / 'cycle-seeds.trace',), report):
        omitted['unqualified'] += 1; return None
    if system == 'snes' and not observations_qualified(
            (supernintendo.memory_file(rom), snes_spc.memory_file(rom)), report):
        omitted['unqualified'] += 1; return None
    record['engine'] = expected_engine
    if system == 'gb':
        record['rom_entries'] = [list(e) for e in sorted(read_entries(gameboy._verified_trace(rom), len(rom.data)))]
    elif system == 'nes':
        directory = library_root('nes') / rom.sha256 / nes.ENGINE_REV
        record['rom_entries'] = [[int(bank,16),int(pc,16)] for _,bank,pc in
            (e.split(':') for e in sorted(nes._seed_sites(directory/'cycle-seeds.trace')))]
        from .nes_ram import opcode_sources, read_sites
        offsets = opcode_sources(rom)
        sites = read_sites(directory / 'cycle-seeds.trace')
        record['ram_opcode_refs'] = [[pc, offsets[op]] for pc, op in sorted(sites) if op in offsets]
        omitted['ram_without_rom_source'] += sum(op not in offsets for _, op in sites)
    else:
        if system == 'md':
            record['rom_entries'] = [[addr] for addr in sorted(megadrive.read_entries(rom))]
            variants = megadrive.read_ram_variants(rom)
        else:
            variants = supernintendo.read_ram_variants(rom)
        refs = []
        for variant in variants:
            raw = bytes.fromhex(variant['bytes']); offset = rom.data.find(raw)
            if offset >= 0: refs.append([variant['address'], offset, len(raw)])
            elif system!='snes': omitted['ram_without_rom_source'] += 1
        record['ram_refs'] = refs
        if system == 'snes':
            offsets = {op: rom.data.find(bytes([op])) for op in range(256)}
            sites=supernintendo.read_ram_opcodes(rom)
            record['ram_opcode_refs']=[[pc,offsets[op]] for pc,op in sites if offsets[op]>=0]
            omitted['ram_without_rom_source']+=sum(offsets[op]<0 for _,op in sites)
            masks = snes_spc.read_masks(rom)
            refs = []
            for pc in range(65536):
                bits = int.from_bytes(masks[pc*32:(pc+1)*32], 'little')
                while bits:
                    bit = bits & -bits; op = bit.bit_length()-1; bits ^= bit
                    if offsets[op] >= 0: refs.append([pc, offsets[op]])
            record['spc_refs'] = refs[:FIELDS['snes']['spc_refs'][1]]
        if system == 'md':
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
    return record


def compact_snes(record: dict) -> None:
    """Lossless run encoding of repeated PC/opcode references. Old snapshots
    remain readable; exact-ROM offsets still reconstruct every guarded byte."""
    refs = record.get('spc_refs', [])
    if refs:
        ranges = compact_spc_refs(refs)
        if len(json.dumps(ranges,separators=(',',':'))) < len(json.dumps(refs,separators=(',',':'))):
            record['spc_ranges'] = ranges
            del record['spc_refs']
    from .snes_knowledge import compact
    compact(record)
