"""Measure how much of what a Super FX game executes a static GSU traversal covers.

Input: the cartridge (a .sfc/.smc file or a zip holding one; read in memory only)
and one or more execution dumps written by an instrumented engine core. A dump is
a JSON object with

  jobs      [[pc24, starts, stops, instructions, gsu_clocks, max_instructions], ...]
            one row per distinct PBR:R15 the S-CPU started the GSU at
  pcs       [[pc24, alt, b, sreg, dreg, origin, opcode, count], ...]
            executed instructions per address and prefix state; origin is
            1 ROM, 2 Game Pak RAM, 3 cache line filled from ROM,
            4 cache line filled from RAM, 5 cache line written by the S-CPU
  indirect  [[pc24, alt, b, sreg, dreg, opcode, target24, count], ...]
            taken non-relative control transfers (JMP, LJMP, LOOP, R15 writes)
  edges     [[from24, to24, count], ...]   optional
            every transition between two executed instructions that is not
            straight-line flow (target 1 to 3 bytes ahead in the same bank)

(The dump format is produced by a local patch of the engine copy in a kept build
folder; nothing in the product writes it.)  Usage:

  python tools/snes_gsu_survey.py --rom "Star Fox (USA).zip" --trace demo.json play.json
"""
import argparse
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrorecomp import snes_gsu as gsu  # noqa: E402

ORIGINS = {1: 'rom', 2: 'ram', 3: 'cache-from-rom', 4: 'cache-from-ram', 5: 'cache-from-cpu'}
MEMORY_CATEGORIES = ('load', 'store')


def read_rom(path):
    path = Path(path)
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(('.sfc', '.smc', '.swc', '.fig'))]
            data = archive.read(names[0])
    else:
        data = path.read_bytes()
    return data[512:] if len(data) % 1024 == 512 else data


@dataclass
class Dump:
    """Merged execution dumps."""
    total: int = 0
    cache_writes: int = 0
    cache_fills: int = 0
    cache_flushes: int = 0
    jobs: dict = field(default_factory=dict)
    pcs: Counter = field(default_factory=Counter)
    indirect: Counter = field(default_factory=Counter)
    edges: Counter = field(default_factory=Counter)
    cbrs: dict = field(default_factory=lambda: defaultdict(Counter))
    sync_calls: int = 0
    sync_clock_log2: list = field(default_factory=lambda: [0] * 40)
    sync_instr_log2: list = field(default_factory=lambda: [0] * 40)


def load_traces(paths):
    merged = Dump()
    jobs = defaultdict(lambda: [0, 0, 0, 0, 0])
    for path in paths:
        dump = json.loads(Path(path).read_text())
        merged.total += dump['total_instructions']
        merged.cache_writes += dump.get('cpu_cache_writes', 0)
        merged.cache_fills += dump.get('cache_fills', 0)
        merged.cache_flushes += dump.get('cache_flushes', 0)
        merged.sync_calls += dump.get('sync_calls_running', 0)
        for key in ('sync_clock_log2', 'sync_instr_log2'):
            for i, value in enumerate(dump.get(key, ())):
                getattr(merged, key)[i] += value
        for pc24, starts, stops, instr, clocks, peak in dump['jobs']:
            row = jobs[pc24]
            row[0] += starts
            row[1] += stops
            row[2] += instr
            row[3] += clocks
            row[4] = max(row[4], peak)
        for row in dump['pcs']:
            pc24, alt, b, sreg, dreg, origin, op, count = row[:8]
            merged.pcs[(pc24, alt, b, sreg, dreg, origin, op)] += count
            if len(row) > 8 and origin in (3, 4, 5):      # CBR only matters to cached fetches
                merged.cbrs[pc24][row[8]] += count
        for pc24, alt, b, sreg, dreg, op, target, count in dump['indirect']:
            merged.indirect[(pc24, alt, b, sreg, dreg, op, target)] += count
        for source, target, count in dump.get('edges', ()):
            merged.edges[(source, target)] += count
    merged.jobs = dict(jobs)
    return merged


def _histogram_share(hist, limits):
    """Percent of calls whose value is below each power-of-two limit, from a log2 histogram."""
    total = sum(hist)
    return {f'<{limit}': round(100 * sum(hist[:limit.bit_length() - 1]) / total, 1) if total else None
            for limit in limits}


def split(pc24):
    return pc24 >> 16, pc24 & 0xffff


def survey(rom_bytes, paths):
    rom = gsu.GsuRom(rom_bytes)
    dump = load_traces(paths)
    jobs, pcs, indirect = dump.jobs, dump.pcs, dump.indirect
    executed = sum(pcs.values())
    out = {'traces': [str(p) for p in paths], 'instructions': executed,
           'cpu_cache_writes': dump.cache_writes}
    if dump.cbrs:
        per_pc = Counter(min(len(v), 4) for v in dump.cbrs.values())
        out['cache'] = {
            'line_fills': dump.cache_fills, 'flushes': dump.cache_flushes,
            'instructions_per_fill': round(executed / dump.cache_fills, 1) if dump.cache_fills else None,
            'pcs_with_n_cbr_values': {('4+' if k == 4 else str(k)): v for k, v in sorted(per_pc.items())},
            'distinct_cbr_values': len({c for v in dump.cbrs.values() for c in v}),
            'executed_under_the_pcs_most_common_cbr_percent': round(
                100 * sum(max(v.values()) for v in dump.cbrs.values())
                / sum(sum(v.values()) for v in dump.cbrs.values()), 2)}
    if dump.sync_calls:
        out['sync_windows'] = {
            'calls_while_running': dump.sync_calls,
            'instructions_per_call_share_percent': _histogram_share(dump.sync_instr_log2, (2, 8, 32, 128, 512, 2048)),
            'master_clocks_per_call_share_percent': _histogram_share(dump.sync_clock_log2, (8, 32, 128, 512, 2048, 8192))}

    # Jobs.
    started = sum(row[0] for row in jobs.values())
    job_instr = sum(row[2] for row in jobs.values())
    job_clocks = sum(row[3] for row in jobs.values())
    out['jobs'] = {
        'distinct_entry_points': len(jobs), 'starts': started,
        'master_clocks_per_instruction': round(job_clocks / job_instr, 2) if job_instr else None,
        'entries': [{'pbr_r15': f'{pc24 >> 16:02X}:{pc24 & 0xffff:04X}', 'starts': row[0],
                     'instructions': row[2], 'instructions_per_job': round(row[2] / row[1]) if row[1] else None,
                     'gsu_clocks': row[3], 'max_instructions': row[4]}
                    for pc24, row in sorted(jobs.items(), key=lambda kv: -kv[1][2])]}

    # Where the executed bytes came from.
    by_origin = Counter()
    for (pc24, alt, b, sreg, dreg, origin, op), count in pcs.items():
        by_origin[origin] += count
    out['origin'] = {ORIGINS.get(k, str(k)): v for k, v in sorted(by_origin.items())}
    ram_total = by_origin[2] + by_origin[4]
    out['game_pak_ram_instructions'] = ram_total
    out['cpu_cache_instructions'] = by_origin[5]
    out['cached_instructions'] = by_origin[3] + by_origin[4] + by_origin[5]

    # Do ROM-origin bytes match the ROM view the decoder reads?
    mismatches = 0
    for (pc24, alt, b, sreg, dreg, origin, op), count in pcs.items():
        if origin in (1, 3):
            pbr, pc = split(pc24)
            if rom.read(pbr, pc) != op:
                mismatches += 1
    out['rom_byte_mismatches'] = mismatches

    # Static traversal from the job entry points.
    entries = [(pc24 >> 16, pc24 & 0xffff) for pc24 in jobs]
    observed = defaultdict(set)
    for (pc24, alt, b, sreg, dreg, op, target), count in indirect.items():
        observed[split(pc24)].add(split(target))
    plain = gsu.traverse(rom, entries)
    resumed = gsu.traverse(rom, entries, resume_after_stop=True)
    seen = gsu.traverse(rom, entries, observed=observed, resume_after_stop=True)
    rows = [(pc24 >> 16, pc24 & 0xffff, (alt, b, sreg, dreg), count)
            for (pc24, alt, b, sreg, dreg, origin, op), count in pcs.items() if origin in (1, 3)]
    rom_executed = sum(r[3] for r in rows)
    out['rom_instructions'] = rom_executed
    out['static_from_entries'] = _coverage(plain, rows, rom_executed, executed)
    out['static_with_stop_resume'] = _coverage(resumed, rows, rom_executed, executed)
    out['static_with_stop_resume']['resume_points'] = len(resumed.resume_points)
    out['static_plus_observed_targets'] = _coverage(seen, rows, rom_executed, executed)
    out['static_plus_observed_targets']['traversal_truncated'] = seen.truncated
    out['static_plus_observed_targets']['resume_points'] = len(seen.resume_points)
    out['static_from_entries']['traversal_truncated'] = plain.truncated

    # The traversal's model of branches and delay slots against every executed transition.
    if dump.edges:
        unexplained = {k: c for k, c in dump.edges.items() if (split(k[0]), split(k[1])) not in seen.edges}
        out['edge_check'] = {
            'dynamic_transitions': len(dump.edges), 'executions': sum(dump.edges.values()),
            'not_in_static_model': len(unexplained), 'not_in_static_model_executions': sum(unexplained.values()),
            'examples': [f'{a >> 16:02X}:{a & 0xffff:04X} to {b >> 16:02X}:{b & 0xffff:04X} x{c}'
                         for (a, b), c in sorted(unexplained.items(), key=lambda kv: -kv[1])[:5]]}

    # Indirect control flow.
    sites = Counter()
    site_targets = defaultdict(Counter)
    site_kind = {}
    for (pc24, alt, b, sreg, dreg, op, target), count in indirect.items():
        sites[pc24] += count
        site_targets[pc24][target] += count
        site_kind[pc24] = _kind(op, alt)
    # `seen` holds every site in code reachable from the entries plus observed
    # targets; a site is statically resolved when constant propagation found its
    # target, and "learned" when only the dump knows it.
    resolved = {k: v for k, v in seen.indirect.items() if v.static_targets}
    unresolved = {k: v for k, v in seen.indirect.items() if not v.static_targets}
    executed_sites = {split(p) for p in site_targets}
    wrong = [k for k, v in resolved.items()
             if v.observed_targets and not v.observed_targets <= v.static_targets]
    learned = {k for k in unresolved if k in executed_sites}
    never = {k for k in unresolved if k not in executed_sites}
    outside = executed_sites - set(seen.indirect)
    kinds = Counter(unresolved[k].kind for k in learned)
    counts = Counter(min(len(unresolved[k].observed_targets), 9) for k in learned)
    by_pc = {split(p): p for p in site_targets}
    out['indirect'] = {
        'sites_in_reached_code': len(seen.indirect),
        'statically_resolved': len(resolved),
        'statically_resolved_but_incomplete': len(wrong),
        'unresolved_executed_in_dump': len(learned),
        'unresolved_by_kind': dict(kinds),
        'unresolved_observed_targets_histogram': {('9+' if k == 9 else str(k)): v
                                                  for k, v in sorted(counts.items())},
        'unresolved_max_observed_targets': max((len(unresolved[k].observed_targets) for k in learned), default=0),
        'unresolved_site_target_pairs': sum(len(unresolved[k].observed_targets) for k in learned),
        'unresolved_never_taken_in_dump': len(never),
        'executed_sites_outside_reached_code': len(outside),
        'taken_transfers_total': sum(sites.values()),
        'taken_transfers_through_unresolved_sites': sum(sites[by_pc[k]] for k in learned),
        'sites': [{'at': f'{p >> 16:02X}:{p & 0xffff:04X}', 'kind': site_kind[p], 'executions': sites[p],
                   'targets': [f'{t >> 16:02X}:{t & 0xffff:04X}' for t, _ in site_targets[p].most_common(6)],
                   'distinct_targets': len(site_targets[p]),
                   'statically_resolved': split(p) in resolved}
                  for p in sorted(site_targets, key=lambda p: -sites[p])[:12]],
    }

    # Prefix-state variety.
    states = defaultdict(set)
    for (pc24, alt, b, sreg, dreg, origin, op) in pcs:
        states[pc24].add((alt, b, sreg, dreg))
    histogram = Counter(min(len(v), 4) for v in states.values())
    nonclear = Counter()
    for (pc24, alt, b, sreg, dreg, origin, op), count in pcs.items():
        nonclear['clear' if (alt, b, sreg, dreg) == gsu.CLEAR else 'prefixed'] += count
    out['prefix_state'] = {
        'distinct_pcs': len(states), 'distinct_pc_state_pairs': sum(len(v) for v in states.values()),
        'pcs_with_n_states': {('4+' if k == 4 else str(k)): v for k, v in sorted(histogram.items())},
        'executed_with_clear_state': nonclear['clear'], 'executed_with_prefix_state': nonclear['prefixed'],
        'pcs_with_several_states': [
            f'{p >> 16:02X}:{p & 0xffff:04X} {sorted(v)}' for p, v in
            sorted(states.items(), key=lambda kv: -len(kv[1])) if len(v) > 1][:8]}

    # Instruction mix and helper tags.
    mix = Counter()
    mnemonics = Counter()
    tags = Counter()
    flow = Counter()
    with_helper = 0
    for (pc24, alt, b, sreg, dreg, origin, op), count in pcs.items():
        pbr, pc = split(pc24)
        instr = gsu.decode_bytes(op, (0, 0), pbr, pc, (alt, b, sreg, dreg))
        mix[instr.category] += count
        mnemonics[instr.mnemonic.split(' ')[0]] += count
        flow[instr.flow] += count
        for tag in instr.tags:
            tags[tag] += count
        if instr.tags:
            with_helper += count
    out['mix'] = {k: _share(v, executed) for k, v in mix.most_common()}
    out['mnemonics_top'] = {k: _share(v, executed) for k, v in mnemonics.most_common(18)}
    out['memory_operations'] = _share(sum(mix[c] for c in MEMORY_CATEGORIES), executed)
    out['helper_tags'] = {k: _share(v, executed) for k, v in tags.most_common()}
    out['needing_an_engine_helper'] = _share(with_helper, executed)
    out['flow'] = {k: _share(v, executed) for k, v in flow.most_common()}

    # Hot spots.
    hot = Counter()
    for (pc24, *_rest, origin, op), count in pcs.items():
        hot[pc24] += count
    top = hot.most_common(20)
    out['hottest'] = {
        'distinct_pcs': len(hot),
        'top20_share_percent': round(100 * sum(c for _, c in top) / executed, 2) if executed else 0,
        'top100_share_percent': round(100 * sum(c for _, c in hot.most_common(100)) / executed, 2) if executed else 0,
        'top20': [{'pc': f'{p >> 16:02X}:{p & 0xffff:04X}', 'share_percent': round(100 * c / executed, 2)}
                  for p, c in top]}
    return out


def _kind(op, alt):
    if op == 0x3c:
        return 'loop'
    if 0x98 <= op <= 0x9d:
        return 'ljmp' if alt & 1 else 'jmp'
    return 'r15'


def _share(count, total):
    return {'count': count, 'percent': round(100 * count / total, 2) if total else 0}


def _coverage(traversal, rows, rom_executed, executed):
    counts = gsu.covered_counts(traversal, rows)
    missed = Counter()
    addresses = traversal.addresses()
    for pbr, pc, state, count in rows:
        if (pbr, pc) not in addresses:
            missed[(pbr << 16) | pc] += count
    return {
        'static_instructions': len(traversal.addresses()),
        'static_pc_state_nodes': len(traversal.nodes),
        'rom_executed_covered_by_address_percent': round(100 * counts['instr_address'] / rom_executed, 3) if rom_executed else 0,
        'rom_executed_covered_by_address_and_state_percent': round(100 * counts['instr_state'] / rom_executed, 3) if rom_executed else 0,
        'all_executed_covered_percent': round(100 * counts['instr_address'] / executed, 3) if executed else 0,
        'executed_distinct_keys_missed': counts['keys_total'] - counts['keys_address'],
        'executed_instructions_missed': rom_executed - counts['instr_address'],
        'missed_pcs_top': [f'{p >> 16:02X}:{p & 0xffff:04X} x{c}' for p, c in missed.most_common(6)],
        'delay_slots_with_operands': len(traversal.slot_operand_sites),
        'unmodelled_transfers': len(traversal.anomalies),
        'unfetchable_targets': len(traversal.not_rom),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--rom', required=True, help='cartridge file or zip (read in memory)')
    parser.add_argument('--trace', nargs='+', required=True, help='execution dumps to merge')
    parser.add_argument('--json', help='write the result here')
    args = parser.parse_args(argv)
    result = survey(read_rom(args.rom), args.trace)
    text = json.dumps(result, indent=1)
    if args.json:
        Path(args.json).write_text(text, encoding='utf-8')
    else:
        print(text)


if __name__ == '__main__':
    main()
