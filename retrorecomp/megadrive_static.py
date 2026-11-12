"""Anchored static discovery of Mega Drive 68000 code.

The decoder follows the code a cartridge's vectors, the engine pass and the learned entries reach, but it never follows
an indirect jump. Most of what a game runs only through a jump table, a table of long pointers or a handler address
stored in RAM is therefore found only once a play route has run it (docs/MEGADRIVE.md, "Discovery").

`anchored_roots` adds roots found from code that is already reached, never from the bytes alone:

* an **anchor** is a reached ROM instruction that loads the address of a table or of a handler, in one of the idioms
  below, and a **window** of the next six instructions (fall-through order, stopped by a terminator) that uses it;
* the tables are read from the table address, 256 entries at most, and stop at the first entry that is odd, below $200 or
  beyond the ROM, at an address that is already a reached instruction start, and at the lowest target above the table;
* every candidate is checked by one **legality test** (illegal decode, illegal opcode, zero word, a suspect opcode for
  the weaker rules, a target out of range, an overlap with reached code, a stub too short) and each refusal is counted
  with exactly one reason;
* the roots accepted in one round are decoded with the others, so a handler found now can anchor another table in the
  next round (twelve rounds at most), within a ceiling of added instructions (`ANCHORED_EXTRA_LIMIT`).

A root is only ever an extra decode root: it never reaches `game.toml`, the learned entries, the library or the base.
A wrong root cannot run as native code, because the generated lookup returns a body for an exact even ROM address and the
body is the decode of the bytes at that address (docs/MEGADRIVE.md).

`anchored_roots` is pure: it reads bytes and decoded instruction dicts through the `decode_fn` it is given and does no
input or output; `static_roots` at the end builds that `decode_fn` for a conversion. A decoded instruction carries the decoder's fields (`addr`, `byte_length`, `words`, `word_count`,
`has_target`, `target_addr`) and a `name`, the mnemonic's `MN_...` name.

Rules (opcode words; tier 1 = a jump really consumes the table, tier 2 = a data candidate):

* a1c  `MOVEA.L (d8,PC,Xn),Am` + `JMP/JSR (Am)`; `LEA/MOVEA.L #` T,An ... `MOVEA.L (d8,An,Xn),Am` + `JMP/JSR (Am)`;
       `ADDI.L #T,Dn` ... `JMP/JSR (d8,Am,Dn.L)`: long pointers
* a2   `LEA T,An` ... `MOVE.W (d8,An,Xn),Dm` + `JMP/JSR (d8,An,Dm)`; `ADDA.W (d8,An,Xn),An` + `JMP/JSR (An)`:
       16-bit offsets relative to T
* a3   `LEA (d8,PC,Xn),An` + `ADDA.W (An),An` + `JMP/JSR (An)`: 16-bit offsets relative to the entry itself
* b1   `MOVE.W (d8,PC,Xn),Dm` + `JMP/JSR (d8,PC,Dm)`: 16-bit offsets relative to the jump base
* b2   `JMP/JSR (d8,PC,Xn)` alone: rows of `BRA.s`, `BRA.w`/`JMP (d16,PC)` or `JMP abs.l` at the base
* c0   the ROM operand of a reached `LEA`/`PEA`/`MOVEA.L #`/`MOVE.L #imm,<ea>` as a code candidate (tier 2)
* c1   the same operand with at least two valid long pointers at it: long pointers (tier 2)
* c2   each c1 pointer that itself holds at least two long pointers (tier 2, off by default)
* a1u  the a1 loads without a jump through the result in the window (tier 2, off by default)
"""
from __future__ import annotations

ANCHORED_EXTRA_LIMIT = 32768      # instructions the roots may add to a conversion; past it a candidate is refused as `cap`
TABLE_LIMIT = 256                 # entries read from one table; a longer one is cut and counted in `tables_cut`
ROUNDS = 12                       # discovery rounds; the last point is left for a later raise and counted (`rounds_exhausted`)
WINDOW = 6                        # instructions after an anchor in which the jump through its result must be
MAPPER_LIMIT = 0x400000           # a banked cartridge above this size is skipped: its pointers are bank dependent
SCHEMA = 1

# The two weakest rules (UMK3: c2 2 wrong of 3; a1u reaches little) run through the same legality test, off by default.
OPTIONAL_RULES = frozenset({'a1u', 'c2'})
ENABLE_OPTIONAL_RULES = False

# Priority when two rules name one target, and the order in which the cap is filled.
RULE_ORDER = ('a1c', 'a2', 'a3', 'b1', 'b2', 'c0', 'c1', 'c2', 'a1u')
TIER2 = frozenset({'a1u', 'c0', 'c1', 'c2'})
MIN_LENGTH = {1: 2, 2: 4}         # instructions on the linear path of a candidate, by tier
REASONS = ('illegal_decode', 'illegal_opcode', 'zero_word', 'suspect_opcode', 'target_out', 'overlap', 'too_short', 'cap')

TERMINATORS = frozenset({'MN_JMP', 'MN_BRA', 'MN_RTS', 'MN_RTE', 'MN_RTR', 'MN_ILLEGAL'})
FLOW = frozenset({'MN_JSR', 'MN_BSR', 'MN_JMP', 'MN_BRA', 'MN_Bcc', 'MN_DBcc'})
ILLEGAL = frozenset({'MN_ILLEGAL', 'MN_OTHER'})
# Tier 2 only. TRAP, ORI/ANDI to SR, ABCD and SBCD are not listed: real handlers start with them.
SUSPECT = frozenset({'MN_STOP', 'MN_RESET', 'MN_TRAPV', 'MN_MOVEC', 'MN_CHK', 'MN_MOVEP', 'MN_TAS', 'MN_NBCD',
                     'MN_MOVE_USP', 'MN_RTR', 'MN_EORI_TO_SR', 'MN_EORI_TO_CCR'})


def enabled_rules() -> tuple[str, ...]:
    return tuple(rule for rule in RULE_ORDER if ENABLE_OPTIONAL_RULES or rule not in OPTIONAL_RULES)


def new_counters(rules=None) -> dict:
    rules = enabled_rules() if rules is None else rules
    return {'schema': SCHEMA, 'rounds': 0, 'rounds_exhausted': False, 'skipped': None, 'tables_cut': 0,
            'rules': {rule: {'targets': 0, 'accepted': 0, 'refused': {reason: 0 for reason in REASONS}} for rule in rules},
            'roots_accepted': 0, 'roots_refused': 0, 'extra_instructions': 0}


def _s8(value: int) -> int:
    value &= 0xff
    return value - 0x100 if value & 0x80 else value


def _s16(value: int) -> int:
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


def _be16(data: bytes, address: int) -> int:
    return int.from_bytes(data[address:address + 2], 'big')


def _be32(data: bytes, address: int) -> int:
    return int.from_bytes(data[address:address + 4], 'big')


def _rom_even(value: int, size: int) -> bool:
    return 0x200 <= value < size and not value & 1


def _words(ins: dict) -> list[int]:
    """The instruction's own words, padded: the decoder's array holds eight words whatever the length."""
    return list(ins['words'][:ins['word_count']]) + [0, 0, 0]


def _index(decoded, size: int) -> dict[int, dict]:
    return {ins['addr']: ins for ins in decoded if ins['addr'] < size}


def _successors(ins: dict) -> list[int]:
    out = []
    if ins['name'] in FLOW and ins['has_target']:
        out.append(ins['target_addr'] & 0xffffff)
    if ins['name'] not in TERMINATORS:
        out.append(ins['addr'] + ins['byte_length'])
    return out


def _window(reached: dict, pc: int):
    """The next instructions in fall-through order, stopped by a terminator or by a gap in the reached code."""
    current = reached[pc]
    for _ in range(WINDOW):
        following = current['addr'] + current['byte_length']
        if current['name'] in TERMINATORS or following not in reached:
            return
        current = reached[following]
        yield current


def _jumps_through(reached: dict, pc: int, register: int) -> bool:
    """`JMP (Am)` or `JSR (Am)` in the window after `pc`."""
    return any(_words(k)[0] in (0x4ed0 | register, 0x4e90 | register) for k in _window(reached, pc))


# ------------------------------------------------------------------ table readers

def _table(data: bytes, start: int, step: int, entry, reached: dict, cuts: set, key) -> list[int]:
    """Walk a table from `start`; `entry(address)` gives `(item, target)` or None for an entry that ends the table.

    The table ends at an address that is a reached instruction start, at the lowest target above the table, and at the
    first invalid entry. A table longer than TABLE_LIMIT is cut there and counted once (`cuts` holds the table keys)."""
    size = len(data)
    if start in reached or not _rom_even(start, size):
        return []
    items, low, address = [], None, start
    while address + step <= size:
        if address in reached or (low is not None and address >= low):
            break
        found = entry(address)
        if found is None:
            break
        if len(items) == TABLE_LIMIT:
            cuts.add(key)
            break
        item, target = found
        items.append(item)
        if target > start:
            low = target if low is None else min(low, target)
        address += step
    return items


def _longs(data: bytes, start: int, reached: dict, cuts: set) -> list[int]:
    size = len(data)

    def entry(address):
        value = _be32(data, address)
        return (value, value) if _rom_even(value, size) else None

    return _table(data, start, 4, entry, reached, cuts, ('long', start))


def _offsets(data: bytes, start: int, base: int | None, reached: dict, cuts: set) -> list[int]:
    """16-bit offsets: relative to `base`, or to the entry itself when `base` is None."""
    size = len(data)

    def entry(address):
        value = ((address if base is None else base) + _s16(_be16(data, address))) & 0xffffff
        if not _rom_even(value, size) or start <= value < address + 2:
            return None
        return value, value

    return _table(data, start, 2, entry, reached, cuts, ('word', start, base))


def _rows(data: bytes, base: int, reached: dict, cuts: set) -> list[int]:
    """Rows of branch instructions at the base of `JMP (d8,PC,Xn)`: the row addresses (the 68000 enters at a row)."""
    size = len(data)
    if not _rom_even(base, size) or base + 2 > size:
        return []
    first = _be16(data, base)
    if first in (0x6000, 0x4efa):
        stride = 4
    elif first == 0x4ef9:
        stride = 6
    elif first & 0xff00 == 0x6000 and first & 0xff not in (0, 0xff) and not first & 1:
        stride = 2
    else:
        return []
    kind = first if stride != 2 else 0x6000

    def entry(address):
        word = _be16(data, address)
        if stride == 2:
            if word & 0xff00 != 0x6000 or word & 0xff in (0, 0xff) or word & 1:
                return None
            target = address + 2 + _s8(word)
        else:
            if word != kind:
                return None
            target = _be32(data, address + 2) & 0xffffff if stride == 6 else address + 2 + _s16(_be16(data, address + 2))
        return (address, target) if _rom_even(target, size) else None

    # No reached filter here: a PC-indexed jump enters at any row, a reached row is no reason to drop the others (the
    # candidate filter in `_candidates` removes the reached ones).
    return _table(data, base, stride, entry, {}, cuts, ('rows', base))


# ------------------------------------------------------------------ anchors

def _candidates(data: bytes, reached: dict, rules: tuple[str, ...], cuts: set) -> dict[int, str]:
    """{target: rule} from the reached ROM instructions; when two rules name a target the first in RULE_ORDER wins."""
    size = len(data)
    on = frozenset(rules)
    rank = {rule: number for number, rule in enumerate(RULE_ORDER)}
    found: dict[int, str] = {}

    def add(rule: str, produce) -> None:
        """`produce()` reads the table; it only runs for a rule that is on."""
        if rule not in on:
            return
        for target in produce():
            if target not in reached and (target not in found or rank[rule] < rank[found[target]]):
                found[target] = rule

    for pc in sorted(reached):
        ins = reached[pc]
        w = _words(ins)
        w0, w1, w2 = w[0], w[1], w[2]
        top = w0 & 0xf1ff
        # A ROM address loaded into An (T) by this instruction; `indexed`: the index is already added into An.
        T = register = None
        indexed = False
        if top == 0x41fa:                                           # LEA (d16,PC),An
            T = pc + 2 + _s16(w1)
        elif top == 0x41f9 or top == 0x207c:                        # LEA abs.l,An ; MOVEA.L #imm,An
            T = ((w1 << 16) | w2) & 0xffffff
        elif top == 0x41f8:                                         # LEA abs.w,An
            T = _s16(w1) & 0xffffff
        elif top == 0x41fb and not w1 & 0x0700:                     # LEA (d8,PC,Xn),An
            T, indexed = pc + 2 + _s8(w1), True
        if T is not None:
            register = (w0 >> 9) & 7
        # ---- a1: long pointers
        if top == 0x207b and not w1 & 0x0700:                       # MOVEA.L (d8,PC,Xn),Am ; JMP/JSR (Am)
            confirmed = _jumps_through(reached, pc, (w0 >> 9) & 7)
            add('a1c' if confirmed else 'a1u', lambda: _longs(data, pc + 2 + _s8(w1), reached, cuts))
        if T is not None and _rom_even(T, size):
            n, added = register, indexed
            for j in _window(reached, pc):
                v = _words(j)
                v0 = v[0]
                if v0 & 0xf1ff in (0x41fa, 0x41f9, 0x41f8, 0x207c) and (v0 >> 9) & 7 == n:
                    break                                           # An reloaded: the window ends
                if v0 == 0xd0f0 | n << 9 | n:                       # ADDA.W (d8,An,Xn),An ; JMP/JSR (An)
                    if _jumps_through(reached, j['addr'], n):
                        add('a2', lambda: _offsets(data, T + _s8(v[1]), T, reached, cuts))
                    break
                if v0 == 0xd0d0 | n << 9 | n:                       # ADDA.W (An),An ; JMP/JSR (An): self-relative words
                    if added and _jumps_through(reached, j['addr'], n):
                        add('a3', lambda: _offsets(data, T, None, reached, cuts))
                    break
                if v0 & 0xf0c0 == 0xd0c0 and (v0 >> 9) & 7 == n:    # ADDA <ea>,An: the index is added
                    added = True
                    continue
                long_indexed = v0 & 0xf03f == 0x2030 | n            # MOVE(A).L (d8,An,Xn),<dst>
                long_indirect = added and v0 & 0xf03f in (0x2010 | n, 0x2018 | n)   # (An) or (An)+ after the ADDA
                if long_indexed or long_indirect:
                    confirmed = False
                    if v0 & 0x01c0 == 0x0040:                       # MOVEA.L -> Am, then JMP/JSR (Am)
                        confirmed = _jumps_through(reached, j['addr'], (v0 >> 9) & 7)
                    add('a1c' if confirmed else 'a1u',
                        lambda: _longs(data, T + (_s8(v[1]) if long_indexed else 0), reached, cuts))
                    break
                if v0 & 0xf1ff == 0x3030 | n:                       # MOVE.W (d8,An,Xn),Dm ; JMP/JSR (d8,An,Dm)
                    m = (v0 >> 9) & 7
                    for k in _window(reached, j['addr']):
                        z = _words(k)
                        if z[0] in (0x4ef0 | n, 0x4eb0 | n) and not z[1] & 0x8000 and (z[1] >> 12) & 7 == m:
                            add('a2', lambda: _offsets(data, T + _s8(v[1]), T + _s8(z[1]), reached, cuts))
                            break
                    break
        if w0 & 0xfff8 == 0x0680:                                   # ADDI.L #T,Dn ; JMP/JSR (d8,Am,Dn.L)
            m, table = w0 & 7, (w1 << 16) | w2
            if _rom_even(table, size) and any(_words(k)[0] & 0xffb8 == 0x4eb0 and
                                              _words(k)[1] & 0xf800 == m << 12 | 0x0800 for k in _window(reached, pc)):
                add('a1c', lambda: _longs(data, table, reached, cuts))
        # ---- b: PC-indexed jumps
        if w0 & 0xf1ff == 0x303b:                                   # MOVE.W (d8,PC,Xn),Dm ; JMP/JSR (d8,PC,Dm)
            m, table = (w0 >> 9) & 7, pc + 2 + _s8(w1)
            for k in _window(reached, pc):
                z = _words(k)
                if z[0] in (0x4efb, 0x4ebb) and not z[1] & 0x8000 and (z[1] >> 12) & 7 == m:
                    add('b1', lambda: _offsets(data, table, k['addr'] + 2 + _s8(z[1]), reached, cuts))
                    break
        if w0 in (0x4efb, 0x4ebb):                                  # JMP/JSR (d8,PC,Xn) alone
            add('b2', lambda: _rows(data, pc + 2 + _s8(w1), reached, cuts))
        # ---- c: a ROM operand that is itself a code or a table candidate (tier 2)
        operand = None
        if T is not None and not indexed:
            operand = T
        elif w0 == 0x4879:                                          # PEA abs.l
            operand = ((w1 << 16) | w2) & 0xffffff
        elif w0 == 0x487a:                                          # PEA (d16,PC)
            operand = pc + 2 + _s16(w1)
        elif w0 & 0xf03f == 0x203c:                                 # MOVE.L #imm,<ea>
            operand = (w1 << 16) | w2
        if operand is not None and _rom_even(operand, size) and operand not in reached:
            add('c0', lambda: (operand,))
            pointers = _longs(data, operand, reached, cuts)
            if len(pointers) >= 2:
                add('c1', lambda: pointers)
                if 'c2' in on:
                    for pointer in pointers:
                        inner = _longs(data, pointer, reached, cuts)
                        if len(inner) >= 2:
                            add('c2', lambda: inner)
    return found


# ------------------------------------------------------------------ legality

def _legality(reached: dict, both: dict, candidates: dict[int, str], size: int) -> tuple[set, dict]:
    """Which candidates decode to a closed, legal stream that never contradicts the reached code.

    `both` is the decode of the reached code and the candidates together. Returns the accepted targets and
    {target: reason} for the others, one reason each."""
    interior: set[int] = set()
    for address, ins in reached.items():
        interior.update(range(address + 2, address + ins['byte_length'], 2))
    bad: dict[int, str] = {}
    predecessors: dict[int, list[int]] = {}
    for address in sorted(both):
        if address in reached:
            continue
        ins = both[address]
        reason = None
        if ins['name'] in ILLEGAL:
            reason = 'illegal_opcode'
        elif ins['name'] in SUSPECT:
            reason = 'suspect_opcode'
        elif ins['words'][0] == 0:
            reason = 'zero_word'
        elif address in interior or any(address + k in reached for k in range(2, ins['byte_length'], 2)):
            reason = 'overlap'
        else:
            for successor in _successors(ins):
                if successor & 1 or successor >= size or successor < 0x200:
                    reason = 'target_out'
                elif successor not in both:
                    reason = 'illegal_decode'
                if reason:
                    break
        if reason:
            bad[address] = reason
        for successor in _successors(ins):
            if successor in both and successor not in reached:
                predecessors.setdefault(successor, []).append(address)

    def spread(seeds: list[int]) -> dict[int, str]:
        cause = {address: bad[address] for address in seeds}
        stack = list(seeds)
        while stack:
            address = stack.pop()
            for before in predecessors.get(address, ()):
                if before not in cause:
                    cause[before] = cause[address]
                    stack.append(before)
        return cause

    everything = spread(sorted(bad))                                # tier 2: every refusal reason
    strict = spread(sorted(a for a, why in bad.items() if why != 'suspect_opcode'))   # tier 1: dispatch-confirmed tables
    accepted: set[int] = set()
    refused: dict[int, str] = {}
    for target in sorted(candidates):
        tier2 = candidates[target] in TIER2
        causes = everything if tier2 else strict
        if target in interior:
            refused[target] = 'overlap'
        elif target not in both:
            refused[target] = 'illegal_decode'
        elif target in causes:
            refused[target] = causes[target]
        else:
            length, address, joined = 0, target, False              # linear length up to a terminator or reached code
            while address in both and length < 64:
                if address in reached:
                    joined = True
                    break
                length += 1
                ins = both[address]
                if ins['name'] in TERMINATORS:
                    if ins['name'] in ('MN_JMP', 'MN_BRA') and ins['has_target'] and length < 8:
                        address = ins['target_addr'] & 0xffffff     # a thunk: keep counting at its target
                        continue
                    break
                address += ins['byte_length']
            if length < MIN_LENGTH[2 if tier2 else 1] and not (joined and length >= 1):
                refused[target] = 'too_short'
            else:
                accepted.add(target)
    return accepted, refused


def _private_closure(target: int, both: dict, reached: dict, taken: set) -> set[int]:
    """The instructions the flow from `target` adds to the reached code and to what other roots already took."""
    added, stack = set(), [target]
    while stack:
        address = stack.pop()
        if address in added or address in reached or address in taken or address not in both:
            continue
        added.add(address)
        stack.extend(_successors(both[address]))
    return added


def _apply_cap(accepted: set, candidates: dict[int, str], both: dict, reached: dict, budget: int) -> tuple[set, set]:
    """Keep the accepted roots, in rule priority then address order, while their added instructions fit the budget."""
    rank = {rule: number for number, rule in enumerate(RULE_ORDER)}
    kept, capped, taken = set(), set(), set()
    for target in sorted(accepted, key=lambda t: (rank[candidates[t]], t)):
        added = _private_closure(target, both, reached, taken)
        if len(added) <= budget:
            kept.add(target)
            taken |= added
            budget -= len(added)
        else:
            capped.add(target)
    return kept, capped


# ------------------------------------------------------------------ entry point

def anchored_roots(data: bytes, decode_fn, seeds, *, mapper: bool) -> tuple[set[int], dict]:
    """Extra decode roots found from the code `seeds` reach, and the counters of the search.

    `decode_fn(pcs)` decodes the flow from `pcs` (a set of addresses) and returns the decoded instructions, each with a
    `name`. A banked cartridge above 4 MiB is skipped (`skipped: 'mapper'`). Deterministic: sorted iteration, a fixed
    rule priority."""
    size = len(data)
    rules = enabled_rules()
    counters = new_counters(rules)
    if mapper and size > MAPPER_LIMIT:
        counters['skipped'] = 'mapper'
        return set(), counters
    seeds = set(seeds)
    reached = _index(decode_fn(set(seeds)), size)
    start = len(reached)
    roots: set[int] = set()
    refused: dict[int, str] = {}
    cuts: set = set()
    for number in range(1, ROUNDS + 1):
        found = _candidates(data, reached, rules, cuts)
        found = {target: rule for target, rule in found.items() if target not in refused and target not in roots}
        if not found:
            break
        counters['rounds'] = number
        for rule in found.values():
            counters['rules'][rule]['targets'] += 1
        both = _index(decode_fn(seeds | roots | set(found)), size)
        accepted, why = _legality(reached, both, found, size)
        budget = ANCHORED_EXTRA_LIMIT - (len(reached) - start)
        accepted, capped = _apply_cap(accepted, found, both, reached, budget)
        why.update({target: 'cap' for target in capped})
        for target in sorted(why):
            counters['rules'][found[target]]['refused'][why[target]] += 1
        refused.update(why)
        for target in accepted:
            counters['rules'][found[target]]['accepted'] += 1
        if not accepted:
            break
        roots |= accepted
        reached = _index(decode_fn(seeds | roots), size)
    else:
        # The last round accepted something: the limit only counts when another round would still have candidates.
        counters['rounds_exhausted'] = any(target not in refused and target not in roots
                                           for target in _candidates(data, reached, rules, cuts))
    counters['tables_cut'] = len(cuts)
    counters['roots_accepted'] = len(roots)
    counters['roots_refused'] = len(refused)
    counters['extra_instructions'] = len(reached) - start
    return roots, counters


def summary_line(counters: dict) -> str:
    """The one conversion-log line (English, like its neighbours)."""
    if counters.get('skipped') == 'mapper':
        return 'Static discovery skipped: a banked cartridge above 4 MiB keeps its pointers bank dependent.'
    capped = sum(rule['refused']['cap'] for rule in counters['rules'].values())

    def count(number: int, noun: str) -> str:
        return f"{number:,} {noun}" + ('' if number == 1 else 's')

    return (f"Static discovery: {count(counters['roots_accepted'], 'root')} from reached code "
            f"(+{count(counters['extra_instructions'], 'instruction')}), "
            f"{count(counters['roots_refused'], 'candidate')} refused ({capped:,} at the cap)."
            + (' The round limit was reached.' if counters['rounds_exhausted'] else ''))


# ------------------------------------------------------------------ the conversion's decoder

def static_roots(engine, project, rom, seeds: set, ram_variants) -> tuple[set, dict]:
    """The extra decode roots of the anchored static discovery and its counters, from the decoder `generate_steps` uses.

    This is the only part of the module that does input and output (the decoder tool, a listing and its output in the
    project folder); it sits here, with the rules it feeds, because only the Mega Drive asks the decoder for them."""
    import json
    from . import megadrive_codegen
    from .core import run
    from .m68000 import mnemonic_names
    from .megadrive import valid_ram_variant
    from .megadrive_hardware import bank_mapper
    # The RAM variants as generate_steps normalises them, so that both decodes reach the same instructions.
    ram = sorted({(0xe00000 | (item['address'] & 0xffff), item['bytes'].lower())
                  for item in ram_variants if valid_ram_variant(item)})
    rom_file, listing, output, data = project / 'cartridge.bin', project / 'static-pcs.txt', project / 'static-decoded.json', rom.data
    state = {}

    # NOTE: this is a second copy of the decode loop of megadrive_codegen (its decode function). That function rebuilds the
    # decoder tool (cmake configure and build under entry_lock) at every call and the discovery decodes some twenty times per
    # pass, so the tool is taken once here and run directly. Fold both into decode(..., tool=None) the next time
    # megadrive_codegen.py is edited anyway (it is shared with the CPS-1, CPS-2 and X68000 stamps, which is why it is not
    # touched for this).
    def decode(pcs):
        if not state:
            state['tool'] = megadrive_codegen.decoder_tool(engine, md_rules=True)
            state['names'] = mnemonic_names(engine)
        pending, examined = set(pcs), set()
        while True:
            pending.update(megadrive_codegen.jump_table_entries(data, pending, examined))
            listing.write_text(''.join(f'{pc:06x}\n' for pc in sorted(pending)) +
                               ''.join(f'{pc:06x}:{raw}\n' for pc, raw in ram), encoding='ascii')
            run([state['tool'], rom_file, listing, output, '--follow-flow'], cwd=project, log=project / 'decode.log')
            decoded = json.loads(output.read_text(encoding='utf-8'))
            reached = {ins['addr'] for ins in decoded if ins['addr'] < len(data)}
            extra = megadrive_codegen.jump_table_entries(data, reached, examined) - reached
            if not extra:
                break
            pending.update(reached | extra)
        for instruction in decoded:
            instruction['name'] = state['names'][instruction['mnemonic']]
        return sorted(decoded, key=lambda ins: (ins['addr'], ins['words']))

    return anchored_roots(data, decode, seeds, mapper=bank_mapper(rom) is not None)
